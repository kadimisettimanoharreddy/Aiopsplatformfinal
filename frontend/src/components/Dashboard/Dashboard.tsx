import { useState, useEffect } from 'react'
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Chip,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Snackbar,
  CircularProgress
} from '@mui/material';
import {
  Build,
  Computer,
  Security,
  Launch,
  Refresh,
  Delete,
  CheckCircle,
  Add
} from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import { infrastructureAPI } from '../../services/api';

// Define the Request interface
interface Request {
  id: string;
  request_identifier: string;
  cloud_provider: string;
  environment: string;
  resource_type: string;
  status: string;
  created_at: string;
  pr_number?: number;
  resources?: {
    console_url: string;
  };
}

export default function Dashboard() {
  const [requests, setRequests] = useState<Request[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [clearDialogOpen, setClearDialogOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearSuccess, setClearSuccess] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  
  // Use the real user from AuthContext
  const { user } = useAuth();

  // Get the timestamp when user last cleared history
  const getClearTimestamp = () => {
    return localStorage.getItem(`clearHistory_${user?.id}`) || '0';
  };

  // Set the timestamp when user clears history
  const setClearTimestamp = () => {
    localStorage.setItem(`clearHistory_${user?.id}`, new Date().toISOString());
  };

  useEffect(() => {
    fetchRequests();
  }, []);

  const fetchRequests = async () => {
    try {
      setLoading(true);
      setError('');
      
      // Use real API call instead of mock data
      const response = await infrastructureAPI.getRequests();
      
      // Handle the response based on your actual API structure
      const requestsData = response.data?.requests || response.data || [];
      
      // Filter requests to show only those created after last clear
      const clearTimestamp = getClearTimestamp();
      const filteredRequests = requestsData.filter((request: Request) => {
        return new Date(request.created_at) > new Date(clearTimestamp);
      });
      
      setRequests(filteredRequests);
      
    } catch (err: any) {
      console.error('Error fetching requests:', err);
      
      // Handle different types of errors
      if (err.response?.status === 401) {
        setError('Authentication failed. Please log in again.');
      } else if (err.response?.status === 403) {
        setError('You do not have permission to view infrastructure requests.');
      } else if (err.response?.status === 404) {
        // No requests found - this is normal for new users
        setRequests([]);
      } else {
        setError('Failed to fetch requests. Please try again.');
      }
      
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    fetchRequests();
  };

  const clearHistory = async () => {
    try {
      setClearing(true);
      setClearDialogOpen(false);
      
      // Set the clear timestamp to now
      setClearTimestamp();
      
      // Clear frontend display (but keep database intact)
      setRequests([]);
      
      // Show success message
      setClearSuccess(true);
      
    } catch (err) {
      setError('Failed to clear history');
      // If API call fails, refetch the data to restore the state
      fetchRequests();
    } finally {
      setClearing(false);
    }
  };

  const getStatusColor = (status: string): "success" | "warning" | "info" | "error" | "default" => {
    switch (status) {
      case 'deployed': return 'success';
      case 'pending': return 'warning';
      case 'pr_created': return 'info';
      case 'failed': return 'error';
      default: return 'default';
    }
  };

  const getEnvironmentChips = () => {
    if (!user?.environment_access) return null;
    
    return Object.entries(user.environment_access)
      .filter(([_, hasAccess]) => hasAccess)
      .map(([env, _]) => (
        <Chip
          key={env}
          label={env.toUpperCase()}
          size="small"
          color={env === 'prod' ? 'error' : env === 'qa' ? 'warning' : 'success'}
          variant="outlined"
          sx={{ mr: 0.5, mb: 0.5 }}
        />
      ));
  };

  const getPendingCount = () => {
    return requests.filter(r => r.status === 'pending' || r.status === 'pr_created').length;
  };

  const getActiveCount = () => {
    return requests.filter(r => r.status === 'deployed').length;
  };

  if (loading && requests.length === 0) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, backgroundColor: '#f0f8ff', minHeight: '100vh' }}>
      <Typography variant="h4" gutterBottom color="#1565c0" fontWeight="bold">
        Infrastructure Dashboard
      </Typography>
      
      <Typography variant="h6" color="#424242" gutterBottom>
        Welcome back, {user?.name || 'User'}!
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Grid container spacing={3} sx={{ mt: 1 }}>
        {/* Environment Access Card */}
        <Grid item xs={12} md={6}>
          <Card sx={{ 
            borderLeft: '4px solid #4caf50',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            borderRadius: 2,
            backgroundColor: '#f1f8e9'
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Security sx={{ mr: 1, color: '#4caf50' }} />
                <Typography variant="h6" color="#2e7d32">Environment Access</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Your current environment permissions:
              </Typography>
              <Box sx={{ mt: 2 }}>
                {getEnvironmentChips()}
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                Department: <span style={{ fontWeight: 500 }}>{user?.department}</span>
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Quick Stats Card */}
        <Grid item xs={12} md={6}>
          <Card sx={{ 
            borderLeft: '4px solid #2196f3',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            borderRadius: 2,
            backgroundColor: '#e3f2fd'
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Build sx={{ mr: 1, color: '#2196f3' }} />
                <Typography variant="h6" color="#1565c0">Infrastructure Stats</Typography>
              </Box>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="#4caf50" fontWeight="bold">
                      {getActiveCount()}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Active Resources
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="#ff9800" fontWeight="bold">
                      {getPendingCount()}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Pending Requests
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
              <Button 
                variant="contained" 
                startIcon={<Add />}
                onClick={() => window.location.href = '/chat'}
                sx={{ mt: 2, backgroundColor: '#1976d2' }}
                fullWidth
              >
                New Request
              </Button>
            </CardContent>
          </Card>
        </Grid>

        {/* Recent Requests Table */}
        <Grid item xs={12}>
          <Card sx={{ 
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            borderRadius: 2,
            backgroundColor: '#fff'
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="h6" color="#1565c0">Recent Infrastructure Requests</Typography>
                <Box>
                  <IconButton 
                    onClick={handleRefresh} 
                    sx={{ mr: 1 }} 
                    disabled={refreshing}
                    title="Refresh requests"
                  >
                    <Refresh />
                  </IconButton>
                  {requests.length > 0 && (
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<Delete />}
                      onClick={() => setClearDialogOpen(true)}
                      color="error"
                      disabled={clearing}
                    >
                      Clear History
                    </Button>
                  )}
                </Box>
              </Box>
              
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow sx={{ backgroundColor: '#e3f2fd' }}>
                      <TableCell><strong>Request ID</strong></TableCell>
                      <TableCell><strong>Cloud</strong></TableCell>
                      <TableCell><strong>Environment</strong></TableCell>
                      <TableCell><strong>Type</strong></TableCell>
                      <TableCell><strong>Status</strong></TableCell>
                      <TableCell><strong>Created</strong></TableCell>
                      <TableCell><strong>Actions</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {requests.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} align="center">
                          <Box sx={{ py: 4 }}>
                            <Typography variant="body2" color="text.secondary">
                              No infrastructure requests yet. Start a chat to create your first resource!
                            </Typography>
                            <Button 
                              variant="contained" 
                              onClick={() => window.location.href = '/chat'}
                              sx={{ mt: 2, backgroundColor: '#1976d2' }}
                            >
                              Start Chat Assistant
                            </Button>
                          </Box>
                        </TableCell>
                      </TableRow>
                    ) : (
                      requests.map((request) => (
                        <TableRow key={request.id} hover>
                          <TableCell>
                            <Typography variant="body2" fontFamily="monospace" color="#424242">
                              {request.request_identifier.split('_').slice(-2).join('_')}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip 
                              label={request.cloud_provider.toUpperCase()} 
                              size="small"
                              color={request.cloud_provider === 'aws' ? 'warning' : 'info'}
                            />
                          </TableCell>
                          <TableCell>
                            <Chip 
                              label={request.environment.toUpperCase()} 
                              size="small"
                              color={request.environment === 'prod' ? 'error' : request.environment === 'qa' ? 'warning' : 'success'}
                            />
                          </TableCell>
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              <Computer sx={{ mr: 1, fontSize: 16, color: '#666' }} />
                              <Typography variant="body2">
                                {request.resource_type.toUpperCase()}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell>
                            <Chip 
                              label={request.status} 
                              size="small"
                              color={getStatusColor(request.status)}
                              icon={request.status === 'deployed' ? <CheckCircle /> : undefined}
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" color="text.secondary">
                              {new Date(request.created_at).toLocaleDateString()}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            {request.status === 'deployed' && request.resources?.console_url && (
                              <IconButton 
                                size="small"
                                onClick={() => window.open(request.resources!.console_url, '_blank')}
                                title="Open Console"
                                color="primary"
                              >
                                <Launch />
                              </IconButton>
                            )}
                            {request.pr_number && (
                              <Button 
                                size="small" 
                                onClick={() => window.open(`https://github.com/your-org/aiops-platform/pull/${request.pr_number}`, '_blank')}
                                sx={{ ml: 1 }}
                                variant="outlined"
                              >
                                PR #{request.pr_number}
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Clear History Dialog */}
      <Dialog open={clearDialogOpen} onClose={() => setClearDialogOpen(false)}>
        <DialogTitle>Clear Request History</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to clear all request history? This action cannot be undone and will remove all infrastructure request records from your dashboard.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setClearDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={clearHistory} 
            color="error" 
            variant="contained"
            disabled={clearing}
          >
            {clearing ? 'Clearing...' : 'Clear History'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Success Snackbar */}
      <Snackbar
        open={clearSuccess}
        autoHideDuration={3000}
        onClose={() => setClearSuccess(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={() => setClearSuccess(false)} severity="success" sx={{ width: '100%' }}>
          History cleared successfully!
        </Alert>
      </Snackbar>
    </Box>
  );
}