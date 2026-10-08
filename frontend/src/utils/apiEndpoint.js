// Backend API endpoint resolution helper
export const getApiEndpoint = () => {
  const envUrl = import.meta.env.VITE_API_URL;
  const savedUrl = localStorage.getItem('__mysql_chat_api_endpoint__') || localStorage.getItem('__sf_chat_api_endpoint__');
  let url = savedUrl || envUrl || 'http://localhost:8000';
  if (url.includes(':8008')) {
    url = url.replace(':8008', ':8000');
  }
  return url;
};

