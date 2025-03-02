console.log('Script loading...');

// CSRF token setup
function getCSRFToken() {
    return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
}

// Function to handle form submissions with fetch API
function submitForm(formElement) {
    console.log(`Setting up form handler for: ${formElement.action}`);
    
    formElement.addEventListener('submit', async (e) => {
        e.preventDefault();
        console.log('Form submitted');
        
        try {
            const formData = new FormData(formElement);
            const response = await fetch(formElement.action, {
                method: formElement.method,
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            console.log('Response status:', response.status);

            if (response.redirected) {
                window.location.href = response.url;
                return;
            }

            const data = await response.json();
            console.log('Response data:', data);

            if (data.message) {
                showMessage(data.message, data.type || 'success');
            }

            if (data.redirect) {
                window.location.href = data.redirect;
            }
        } catch (error) {
            console.error('Form submission error:', error);
            showMessage('An error occurred. Please try again.', 'error');
        }
    });
}

// Function to show flash messages
function showMessage(message, type = 'success') {
    console.log(`Showing message: ${message} (${type})`);
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `max-w-7xl mx-auto px-4 py-2`;
    messageDiv.innerHTML = `
        <div class="rounded-md p-4 ${type === 'error' ? 'bg-red-50 text-red-800' : 'bg-green-50 text-green-800'}">
            ${message}
        </div>
    `;
    
    const container = document.querySelector('nav').nextElementSibling;
    container.parentNode.insertBefore(messageDiv, container);

    setTimeout(() => messageDiv.remove(), 5000);
}

// Function to handle button clicks
function handleButtonClick(button) {
    console.log(`Setting up button handler for: ${button.dataset.action}`);
    
    button.addEventListener('click', async (e) => {
        e.preventDefault();
        console.log(`Button clicked: ${button.dataset.action}`);

        if (button.dataset.action === 'delete' && !confirm('Are you sure you want to proceed with this action?')) {
            return;
        }

        try {
            const response = await fetch(button.dataset.url, {
                method: button.dataset.method || 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json'
                }
            });

            console.log('Response status:', response.status);

            if (response.redirected) {
                window.location.href = response.url;
                return;
            }

            const data = await response.json();
            console.log('Response data:', data);

            if (data.message) {
                showMessage(data.message, data.type || 'success');
            }

            if (data.redirect) {
                window.location.href = data.redirect;
            }

            // Handle file download for export action
            if (button.dataset.action === 'export' && data) {
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'user_data.json';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            }
        } catch (error) {
            console.error('Button click error:', error);
            showMessage('An error occurred. Please try again.', 'error');
        }
    });
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded - initializing handlers');

    // Add CSRF token meta tag
    const meta = document.createElement('meta');
    meta.name = 'csrf-token';
    meta.content = document.querySelector('meta[name="csrf-token"]')?.content || '';
    document.head.appendChild(meta);

    // Initialize forms
    const forms = document.querySelectorAll('form:not(.no-ajax)');
    console.log(`Found ${forms.length} forms to initialize`);
    forms.forEach(submitForm);

    // Initialize buttons
    const buttons = document.querySelectorAll('button[data-action]');
    console.log(`Found ${buttons.length} buttons to initialize`);
    buttons.forEach(handleButtonClick);

    console.log('Initialization complete');
});

// Immediate console log to verify script loading
console.log('Script loaded successfully'); 