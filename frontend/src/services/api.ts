import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Create axios instance
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle common errors
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid
      localStorage.removeItem('token');
      delete api.defaults.headers.common['Authorization'];
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Infrastructure API endpoints
export const infrastructureAPI = {
  // Get all infrastructure requests
  getRequests: () => api.get('/infrastructure/requests'),
  // Create new infrastructure request
  createRequest: (data: any) => api.post('/infrastructure/request', data),
  // Get specific request by ID
  getRequest: (id: string) => api.get(`/infrastructure/requests/${id}`),
  // Update request status
  updateRequest: (id: string, data: any) => api.put(`/infrastructure/requests/${id}`, data),
  // Delete/cancel request
  deleteRequest: (id: string) => api.delete(`/infrastructure/requests/${id}`),
  // Get available cloud providers
  getCloudProviders: () => api.get('/infrastructure/cloud-providers'),
  // Get available environments
  getEnvironments: () => api.get('/infrastructure/environments'),
  // Get resource types
  getResourceTypes: () => api.get('/infrastructure/resource-types'),
};

// Auth API endpoints
export const authAPI = {
  login: (email: string, password: string) => api.post('/auth/login', { email, password }),
  register: (userData: any) => api.post('/auth/register', userData),
  verifyOTP: (email: string, otp: string) => api.post('/auth/verify-otp', { email, otp }),
  getProfile: () => api.get('/auth/profile'),
  updateProfile: (data: any) => api.put('/auth/profile', data),
  changePassword: (data: any) => api.post('/auth/change-password', data),
  logout: () => api.post('/auth/logout'),
};

// Chat API endpoints
export const chatAPI = {
  sendMessage: (message: string) => api.post('/chat/message', { message }),
  getChatHistory: () => api.get('/chat/history'),
  clearChatHistory: () => api.delete('/chat/history'),
};

// Notification API endpoints
export const notificationAPI = {
  getNotifications: () => api.get('/notifications'),
  markAsRead: (id: string) => api.put(`/notifications/${id}/read`),
  markAllAsRead: () => api.put('/notifications/mark-all-read'),
};

// Settings API endpoints
export const settingsAPI = {
  getSettings: () => api.get('/settings'),
  updateSettings: (data: any) => api.put('/settings', data),
  getEnvironmentAccess: () => api.get('/settings/environment-access'),
  requestEnvironmentAccess: (environment: string) => api.post('/settings/request-environment-access', { environment }),
};

// Default export
export default api;