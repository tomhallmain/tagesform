import requests
import logging
from flask import current_app
from ..utils.config import config

logger = logging.getLogger(__name__)

class OllamaService:
    def __init__(self):
        self.base_url = config.OLLAMA_BASE_URL
        self.model = config.OLLAMA_MODEL

    def query(self, prompt, model=None):
        """Send a query to Ollama's API and return the response"""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model or self.model,
                    "prompt": prompt,
                    "stream": False
                }
            )
            response.raise_for_status()
            return response.json()['response']
        except requests.exceptions.RequestException as e:
            logger.error(f"Error querying Ollama: {e}")
            return None

    def check_connection(self):
        """Check if Ollama service is available"""
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

# Create a singleton instance
ollama_service = OllamaService() 