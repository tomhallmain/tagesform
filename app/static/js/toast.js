// Toast notification function
window.showToast = function(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `${type === 'success' ? 'bg-green-500' : 'bg-red-500'} text-white px-6 py-4 rounded-lg shadow-lg mb-4 transition-opacity duration-500`;
    toast.style.opacity = '0';
    toast.innerHTML = message;
    
    const container = document.getElementById('toast-container');
    if (!container) {
        console.error('Toast container not found');
        return;
    }
    
    container.appendChild(toast);
    
    // Fade in
    setTimeout(() => {
        toast.style.opacity = '1';
    }, 10);
    
    // Fade out and remove after 3 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            container.removeChild(toast);
        }, 500);
    }, 3000);
}; 