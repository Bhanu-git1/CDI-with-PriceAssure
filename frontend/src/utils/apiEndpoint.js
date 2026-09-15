// Backend API endpoint resolution helper
export const getApiEndpoint = () => {
  const envUrl = import.meta.env.VITE_API_URL;
  const savedUrl = localStorage.getItem('__mysql_chat_api_endpoint__') || localStorage.getItem('__sf_chat_api_endpoint__');
  return savedUrl || envUrl || 'http://localhost:8008';
};
