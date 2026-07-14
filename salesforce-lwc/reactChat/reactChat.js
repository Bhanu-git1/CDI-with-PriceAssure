import { LightningElement, api } from 'lwc';
import { loadScript, loadStyle } from 'lightning/platformResourceLoader';
import SF_CHAT_BUNDLE from '@salesforce/resourceUrl/sfChatBundle';
import Id from '@salesforce/user/Id';

/**
 * reactChat - Lightning Web Component
 * 
 * Wraps the React-based MCP Salesforce Chat UI inside a Salesforce Custom Tab.
 * The React app is loaded from a Static Resource (sfChatBundle) and mounted
 * into a manually-controlled DOM container.
 * 
 * DEPLOYMENT STEPS:
 * 1. Build the React frontend: cd frontend && npm run build
 * 2. Zip the contents of frontend/dist/ into sfChatBundle.zip
 * 3. Upload sfChatBundle.zip as a Static Resource named "sfChatBundle" in Salesforce Setup
 * 4. Deploy this LWC component to your Salesforce org
 * 5. Create a Custom Tab using this component (via App Manager)
 */
export default class ReactChat extends LightningElement {
    /**
     * The URL of the FastAPI backend server.
     * Set this in the component configuration when adding to a Lightning Page.
     * Example: https://your-backend-server.com
     */
    // @api apiEndpoint = 'http://localhost:8000';
    @api apiEndpoint = 'https://shack-urethane-heap.ngrok-free.dev';

    userId = Id;
    reactLoaded = false;
    error = null;

    renderedCallback() {
        if (this.reactLoaded) {
            return;
        }
        this.reactLoaded = true;

        // Create the mount point div inside the lwc:dom="manual" container
        const container = this.template.querySelector('.react-root');
        const mountDiv = document.createElement('div');
        mountDiv.id = 'sf-chat-root';
        mountDiv.style.width = '100%';
        mountDiv.style.height = '100vh';
        container.appendChild(mountDiv);

        // CRITICAL: Pass mount element via window global because
        // document.getElementById() cannot find elements inside LWC Shadow DOM.
        // The React app's main.jsx checks window.__SF_CHAT_MOUNT__ first.
        window.__SF_CHAT_MOUNT__ = mountDiv;

        // Inject Salesforce context for the React app to consume
        window.__SF_CHAT_CONFIG__ = {
            userId: this.userId,
            apiEndpoint: this.apiEndpoint,
            sessionId: null,
            instanceUrl: null,
            platform: 'salesforce-lwc'
        };

        // Try loading CSS (non-blocking — CSS might be inlined in JS bundle)
        loadStyle(this, SF_CHAT_BUNDLE + '/sfchat.css')
            .then(() => {
                console.log('MCP Chat: CSS loaded from Static Resource.');
            })
            .catch((cssErr) => {
                console.warn('MCP Chat: External CSS not found, styles may be bundled in JS.', cssErr.message);
            });

        // Load the JS bundle — this is the critical load
        loadScript(this, SF_CHAT_BUNDLE + '/sfchat.js')
            .then(() => {
                console.log('MCP Salesforce Chat UI loaded successfully.');
            })
            .catch((err) => {
                this.error = err.message || 'Failed to load chat interface.';
                console.error('Error loading React chat bundle:', err);

                // Show error message in the container
                const errorDiv = document.createElement('div');
                errorDiv.style.cssText = 'padding:40px;text-align:center;color:#ea001e;font-family:sans-serif;';
                errorDiv.innerHTML = `
                    <h3 style="margin-bottom:12px;">⚠️ Failed to load Chat UI</h3>
                    <p style="color:#706e6b;margin-top:8px;">${this.error}</p>
                    <p style="color:#706e6b;margin-top:12px;font-size:0.85rem;">
                        Checklist:<br/>
                        1. Static Resource named <strong>sfChatBundle</strong> exists<br/>
                        2. It contains <strong>sfchat.js</strong><br/>
                        3. Cache Control is set to <strong>Public</strong>
                    </p>
                `;
                container.appendChild(errorDiv);
            });
    }
}
