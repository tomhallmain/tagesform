"""General LLM interface using Ollama."""

from dataclasses import dataclass
import json
import math
import random
import threading
import time
from typing import Optional, List
from urllib import request
from urllib.error import HTTPError

from app.utils.config import config
from app.utils.logging_setup import get_logger
from app.utils.utils import Utils

logger = get_logger(__name__)

class LLMResponseException(Exception):
    """Raised when LLM call fails"""
    pass


class LLMBatchStoppingException(LLMResponseException):
    """Base class for LLM failures that mean a caller running a batch of requests (e.g. bulk
    translation) should stop entirely rather than skip this item and continue - the condition
    won't resolve by moving on to the next call, so continuing would just repeat the same
    failure for every remaining item.
    """
    pass


class LLMRateLimitException(LLMBatchStoppingException):
    """Raised when the LLM provider responds with HTTP 429 (rate limited)."""
    pass


class LLMForbiddenException(LLMBatchStoppingException):
    """Raised when the LLM provider responds with HTTP 403 (forbidden) - e.g. the model requires
    a paid subscription the account doesn't have, or the client isn't authenticated/signed in.
    """
    pass


@dataclass
class LLMResult:
    """Encapsulates the response data from an Ollama LLM call."""
    response: str
    context: Optional[List[int]]
    context_provided: bool
    created_at: str
    done: bool
    done_reason: Optional[str]
    total_duration: int
    load_duration: int
    prompt_eval_count: int
    prompt_eval_duration: int
    eval_count: int
    eval_duration: int

    @classmethod
    def from_json(cls, data: dict, context_provided=False) -> 'LLMResult':
        """Create a LLMResult instance from the JSON response data."""
        return cls(
            response=data.get("response", ""),
            context=data.get("context", None),
            context_provided=context_provided,
            created_at=data.get("created_at", ""),
            done=data.get("done", False),
            done_reason=data.get("done_reason", ""),
            total_duration=data.get("total_duration", 0),
            load_duration=data.get("load_duration", 0),
            prompt_eval_count=data.get("prompt_eval_count", 0),
            prompt_eval_duration=data.get("prompt_eval_duration", 0),
            eval_count=data.get("eval_count", 0),
            eval_duration=data.get("eval_duration", 0)
        )

    def validate(self):
        if self.response is None or self.response.strip() == "":
            return False
        return True

    def get_json_dict(self):
        """Parse the raw response into a JSON object, tolerating code fences and a leading "json" tag.

        Returns:
            Optional[dict]: The parsed JSON object, or None if the response is empty/malformed.
        """
        try:
            json_str = self.response
            if json_str is None or json_str.strip() == "" or ("{" not in json_str or "}" not in json_str or ":" not in json_str):
                raise Exception("No or malformed JSON object found in JSON string!")
            json_str = json_str.replace("```", "").strip()
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()
            json_obj = json.loads(json_str)
            assert isinstance(json_obj, dict)
            return json_obj
        except Exception as e:
            logger.error(f"{e} - Failed to parse JSON object from response: {self.response}")
            return None

    def _get_json_attr(self, attr_name):
        try:
            if attr_name is None or attr_name.strip() == "":
                raise Exception(f"Invalid attr name: \"{attr_name}\"")
            json_obj = self.get_json_dict()
            if json_obj is None:
                return None
            if attr_name not in json_obj:
                for key in json_obj.keys():
                    if Utils.is_similar_strings(attr_name, key):
                        self.response = json_obj[key]
                        return self
                raise Exception(f"Key \"{attr_name}\" not found in JSON response")
            self.response = json_obj[attr_name]
            return self
        except Exception as e:
            logger.error(f"{e} - Failed to get json attr {attr_name} from json response: {self.response}")
            return None


class LLM:
    """
    Interface for interacting with the Ollama LLM API.
    
    TODO: Consider implementing redundancy elimination during response generation.
    This would require:
    1. Setting up streaming responses from the LLM
    2. Checking each chunk as it arrives
    3. Short-circuiting response generation if redundancy is detected
    4. This would save both processing time and API costs
    """
    DEFAULT_TIMEOUT = 180
    DEFAULT_SYSTEM_PROMPT_DROP_RATE = 0.9  # 90% chance to drop system prompt
    CHECK_INTERVAL = 0.1  # How often to check for cancellation
    DEFAULT_CJK_REJECT_THRESHOLD_PERCENTAGE = 50
    FAILURE_THRESHOLD = 3  # Number of consecutive failures before considering LLM unavailable
    DEFAULT_STATE = "local"  # Default state key for instances without a specific state
    
    # Class-level failure tracking: maps state keys to failure counts
    _failure_counts = {}

    def __init__(self, model_name=None, run_context=None, state_key=None):
        self.model_name = model_name or config.OLLAMA_MODEL
        self.run_context = run_context
        self.state_key = state_key if state_key is not None else LLM.DEFAULT_STATE
        self._cancelled = False
        self._result = None
        self._exception = None
        self._thread = None
        logger.info(f"Using LLM model: {self.model_name} (state: {self.state_key})")

    @classmethod
    def _get_failure_count_for_state(cls, state_key):
        """Get the failure count for a specific state."""
        return cls._failure_counts.get(state_key, 0)

    @classmethod
    def _increment_failure_count_for_state(cls, state_key):
        """Increment the failure count for a specific state."""
        if state_key not in cls._failure_counts:
            cls._failure_counts[state_key] = 0
        cls._failure_counts[state_key] += 1
        logger.warning(f"LLM failure count increased to {cls._failure_counts[state_key]} for state '{state_key}'")

    @classmethod
    def _reset_failure_count_for_state(cls, state_key):
        """Reset the failure count for a specific state."""
        if state_key in cls._failure_counts and cls._failure_counts[state_key] > 0:
            logger.info(f"Resetting LLM failure count from {cls._failure_counts[state_key]} to 0 for state '{state_key}'")
        cls._failure_counts[state_key] = 0

    @classmethod
    def _is_failing_for_state(cls, state_key):
        """Check if the LLM is in a failing state for a specific state key."""
        return cls._get_failure_count_for_state(state_key) >= cls.FAILURE_THRESHOLD

    def get_failure_count(self):
        """Get the failure count for this instance's state."""
        return self._get_failure_count_for_state(self.state_key)

    def increment_failure_count(self):
        """Increment the failure count for this instance's state."""
        self._increment_failure_count_for_state(self.state_key)

    def reset_failure_count(self):
        """Reset the failure count for this instance's state."""
        self._reset_failure_count_for_state(self.state_key)

    def is_failing(self):
        """Check if the LLM is in a failing state for this instance's state."""
        return self._is_failing_for_state(self.state_key)

    @classmethod
    def is_failing_for_state(cls, state_key=None):
        """Check if the LLM is in a failing state for a specific state (or default)."""
        if state_key is None:
            state_key = cls.DEFAULT_STATE
        return cls._is_failing_for_state(state_key)

    def get_llm_penalty(self):
        """Get penalty value based on failure count for this instance's state."""
        return 1.0 / (1.0 + math.log2(1.0 + self.get_failure_count()))

    def ask(self, query, json_key=None, timeout=DEFAULT_TIMEOUT, context=None, system_prompt=None,
            system_prompt_drop_rate=DEFAULT_SYSTEM_PROMPT_DROP_RATE,
            cjk_reject_threshold_percentage=DEFAULT_CJK_REJECT_THRESHOLD_PERCENTAGE):
        """Ask the LLM a question and optionally extract a JSON value."""
        logger.debug(f"LLM.ask called with query length: {len(query)}, json_key: {json_key}")
        if json_key is not None:
            return self.generate_json_get_value(
                query,
                json_key,
                timeout=timeout,
                context=context,
                system_prompt=system_prompt,
                system_prompt_drop_rate=system_prompt_drop_rate,
                cjk_reject_threshold_percentage=cjk_reject_threshold_percentage,
            )
        return self.generate_response_async(
            query,
            timeout=timeout,
            context=context,
            system_prompt=system_prompt,
            system_prompt_drop_rate=system_prompt_drop_rate,
            cjk_reject_threshold_percentage=cjk_reject_threshold_percentage,
        )

    def generate_response(self, query, timeout=DEFAULT_TIMEOUT, context=None, system_prompt=None,
                          system_prompt_drop_rate=DEFAULT_SYSTEM_PROMPT_DROP_RATE,
                          cjk_reject_threshold_percentage=DEFAULT_CJK_REJECT_THRESHOLD_PERCENTAGE):
        """Generate a response from the LLM."""
        logger.debug(f"LLM.generate_response called with query length: {len(query)}")
        query = self._sanitize_query(query)
        timeout = self._get_timeout(timeout)
        logger.debug(f"Asking LLM {self.model_name}:\n{query}")
        data = {
            "model": self.model_name,
            "prompt": query,
            "stream": False,
            # Without num_ctx, Ollama silently uses whatever context window
            # the model was pulled with -- often far smaller than a large
            # prompt (e.g. a several-hundred-task overview) actually needs,
            # so the model just never sees everything the caller thinks it
            # sent. Configurable since it trades off against the model's
            # supported max and the host's available VRAM/RAM.
            "options": {
                "num_ctx": config.OLLAMA_NUM_CTX,
            },
        }
        
        if context is not None:
            data["context"] = context
            logger.debug(f"Adding context to LLM request, length: {len(context)}")
            
        # Randomly decide whether to include system prompt
        if system_prompt is not None and random.random() > system_prompt_drop_rate:
            data["system"] = system_prompt
            logger.debug("Including system prompt in LLM request")
        elif system_prompt is not None:
            logger.debug("Dropping system prompt from LLM request")
            
        req = request.Request(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            headers={"Content-Type": "application/json"},
            data=json.dumps(data).encode("utf-8"),
        )
        try:
            logger.debug("Making LLM request...")
            response = request.urlopen(req, timeout=timeout).read().decode("utf-8")
            resp_json = json.loads(response)
            result = LLMResult.from_json(resp_json, context_provided=context is not None)
            result.response = self._clean_response_for_models(
                result.response,
                cjk_reject_threshold_percentage=cjk_reject_threshold_percentage,
            )
            logger.debug(f"LLM response received, length: {len(result.response)}")
            if result.validate():
                # Reset LLM failure count on success
                self.reset_failure_count()
            else:
                raise LLMResponseException("LLM response is invalid!")
            return result
        except HTTPError as e:
            self.increment_failure_count()
            if e.code == 429:
                message = self._build_http_error_message(
                    "Rate limited by the LLM provider (HTTP 429).", e, include_retry_after=True
                )
                logger.error(f"Rate limited by LLM provider (model {self.model_name}): {message}")
                raise LLMRateLimitException(message) from e
            if e.code == 403:
                message = self._build_http_error_message(
                    "Forbidden by the LLM provider (HTTP 403).", e
                )
                logger.error(f"Forbidden by LLM provider (model {self.model_name}): {message}")
                raise LLMForbiddenException(message) from e
            logger.error(f"Failed to generate LLM response: {e}")
            raise LLMResponseException(f"Failed to generate LLM response: {e}")
        except Exception as e:
            logger.error(f"Failed to generate LLM response: {e}")
            self.increment_failure_count()  # Increment on LLM failure
            raise LLMResponseException(f"Failed to generate LLM response: {e}")

    @staticmethod
    def _build_http_error_message(prefix: str, error: HTTPError, include_retry_after: bool = False) -> str:
        """Build a human-readable message for an HTTP error response, using the server's JSON
        error body (Ollama's error responses are ``{"error": "..."}"``) and, for rate limiting,
        the Retry-After header, when available."""
        server_message = ""
        try:
            body = error.read().decode("utf-8")
            if body:
                parsed = json.loads(body)
                if isinstance(parsed, dict) and parsed.get("error"):
                    server_message = str(parsed["error"])
        except Exception:
            pass

        parts = [prefix]
        if server_message:
            parts.append(server_message)
        if include_retry_after:
            retry_after = error.headers.get("Retry-After") if error.headers else None
            if retry_after:
                parts.append(f"Retry after {retry_after} seconds.")
        return " ".join(parts)

    def generate_response_async(self, query, timeout=DEFAULT_TIMEOUT, context=None, system_prompt=None,
                                system_prompt_drop_rate=DEFAULT_SYSTEM_PROMPT_DROP_RATE,
                                cjk_reject_threshold_percentage=DEFAULT_CJK_REJECT_THRESHOLD_PERCENTAGE):
        """Generate a response from the LLM in a separate thread with cancellation support."""
        logger.debug(f"LLM.generate_response_async called with query length: {len(query)}")
        self._cancelled = False
        self._result = None
        self._exception = None
        self._thread = None

        def run_generation():
            try:
                logger.debug("Starting LLM generation in thread")
                result = self.generate_response(
                    query,
                    timeout,
                    context,
                    system_prompt,
                    system_prompt_drop_rate,
                    cjk_reject_threshold_percentage,
                )
                if not self._cancelled:
                    self._result = result
                    logger.debug("LLM generation completed successfully")
                else:
                    logger.debug("LLM generation cancelled before completion")
            except Exception as e:
                self._exception = e
                logger.error(f"Exception in LLM generation thread: {e}")

        # Start the generation in a separate thread
        self._thread = threading.Thread(target=run_generation)
        self._thread.daemon = True  # Make it a daemon thread so it won't prevent program exit
        self._thread.start()
        logger.debug("LLM generation thread started")

        # Wait for completion or cancellation
        try:
            while self._thread and self._thread.is_alive():
                if self.run_context and self.run_context.should_skip():
                    logger.debug("Cancelling LLM generation due to skip request")
                    self._cancelled = True
                    # Give the thread a moment to clean up
                    self._thread.join(timeout=1.0)
                    if self._thread.is_alive():
                        logger.error("Thread did not terminate gracefully, forcing cleanup")
                    self._thread = None  # Force cleanup even if thread is still alive
                    return None
                time.sleep(self.CHECK_INTERVAL)
        except Exception as e:
            self._exception = e
            logger.error(f"Exception while monitoring LLM thread: {e}")
        finally:
            self._thread = None  # Clean up thread reference when done

        # Handle the result
        if self._exception:
            logger.error(f"Failed to generate LLM response: {self._exception}")
            if isinstance(self._exception, LLMBatchStoppingException):
                # Re-raise as-is so callers can distinguish "should stop" failures (rate limit,
                # forbidden/subscription) from other failures; wrapping it below would lose that.
                raise self._exception
            raise LLMResponseException(f"Failed to generate LLM response: {self._exception}")
        
        return self._result

    def generate_json_get_value(self, query, json_key, timeout=DEFAULT_TIMEOUT, context=None, system_prompt=None,
                                system_prompt_drop_rate=DEFAULT_SYSTEM_PROMPT_DROP_RATE,
                                cjk_reject_threshold_percentage=DEFAULT_CJK_REJECT_THRESHOLD_PERCENTAGE):
        """Generate a response and extract a specific JSON value."""
        result = self.generate_response_async(
            query,
            timeout=timeout,
            context=context,
            system_prompt=system_prompt,
            system_prompt_drop_rate=system_prompt_drop_rate,
            cjk_reject_threshold_percentage=cjk_reject_threshold_percentage,
        )
        if result is None:
            raise LLMResponseException("Failed to generate LLM response - Result is None")
        return result._get_json_attr(json_key)

    def generate_json_dict(self, query, timeout=DEFAULT_TIMEOUT, context=None, system_prompt=None,
                           system_prompt_drop_rate=DEFAULT_SYSTEM_PROMPT_DROP_RATE,
                           cjk_reject_threshold_percentage=DEFAULT_CJK_REJECT_THRESHOLD_PERCENTAGE):
        """Generate a response and parse it as a JSON object, e.g. one key per requested locale.

        Unlike :meth:`generate_json_get_value`, this returns the whole parsed object rather than
        a single key's value, so callers can request several results (such as translations for
        multiple locales) in a single LLM call.
        """
        result = self.generate_response_async(
            query,
            timeout=timeout,
            context=context,
            system_prompt=system_prompt,
            system_prompt_drop_rate=system_prompt_drop_rate,
            cjk_reject_threshold_percentage=cjk_reject_threshold_percentage,
        )
        if result is None:
            raise LLMResponseException("Failed to generate LLM response - Result is None")
        return result.get_json_dict()

    def _is_thinking_model(self) -> bool:
        """Check if the current model is a thinking model that uses internal prompts."""
        return self.model_name.startswith("deepseek-r1")

    def _clean_response_for_models(self, response_text,
                                   cjk_reject_threshold_percentage=DEFAULT_CJK_REJECT_THRESHOLD_PERCENTAGE):
        """
        Clean and validate model responses, handling model-specific patterns and invalid outputs.
        
        Args:
            response_text: The raw response text from the model
            cjk_reject_threshold_percentage: CJK ratio percentage (0-100) above which responses are rejected.
                                           Use None to disable this check.
        
        Returns:
            str: Cleaned response text, or empty string if the response is invalid
            
        Note:
            CJK-heavy characters are rejected by default because they are not supported by the Coqui TTS model
            used in this application. This includes Chinese (Han), Japanese (Hiragana, Katakana, Kanji),
            and Korean (Hangul) characters.
        """
        # First handle thinking model specific cleaning
        if self._is_thinking_model():
            if response_text.strip().startswith("<think>") and "</think>" in response_text:
                response_text = response_text[response_text.rfind("</think>") + len("</think>"):].strip()
            if "<think>" in response_text:
                # Sometimes the model will return extra misplaced <think> tags in the non-thinking section of the response.
                response_text = response_text.replace("<think>", "").replace("</think>", "").strip()

        # Remove "Final Answer:" prefix if present
        if response_text.strip().startswith("Final Answer:"):
            response_text = response_text[response_text.find("Final Answer:") + len("Final Answer:"):].strip()

        # Reject mostly CJK responses when threshold checking is enabled.
        if (cjk_reject_threshold_percentage is not None and
                Utils.get_cjk_character_ratio(response_text, cjk_reject_threshold_percentage)):
            return ""

        # Check for invalid output pattern (Chinese characters followed by note block)
        invalid_pattern = "---\n\n**Note:** The assistant's response is cut off due to the user stopping the interaction.\n\n---"
        if invalid_pattern in response_text:
            # If the response is just the invalid pattern, return empty string
            if response_text.strip() == invalid_pattern:
                return ""
            
            # Check if the text before the invalid pattern is mostly CJK characters
            before_pattern = response_text[:response_text.find(invalid_pattern)].strip()
            if (cjk_reject_threshold_percentage is not None and
                    Utils.get_cjk_character_ratio(before_pattern, cjk_reject_threshold_percentage)):
                return ""
            
            # Otherwise, just remove the invalid pattern
            response_text = response_text.replace(invalid_pattern, "").strip()

        return response_text

    def _sanitize_query(self, query):
        return query

    def _get_timeout(self, timeout=DEFAULT_TIMEOUT):
        if self._is_thinking_model():
            # Thinking models have internal prompt mechanisms which
            # can take a while to complete for complex requests.
            return max(timeout, 300)
        return timeout

    def cancel_generation(self):
        """Cancel any ongoing LLM generation."""
        logger.info("Cancelling LLM generation")
        if self._thread and self._thread.is_alive():
            self._cancelled = True
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():
                logger.error("Thread did not terminate gracefully, forcing cleanup")
            self._thread = None  # Force cleanup even if thread is still alive

    def __del__(self):
        """Ensure cleanup on object destruction."""
        self.cancel_generation()


if __name__ == "__main__":
    llm = LLM()
    print(llm.generate_response("What is the meaning of life?"))
