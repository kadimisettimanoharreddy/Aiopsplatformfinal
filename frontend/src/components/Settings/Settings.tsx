
import { useState, useEffect } from 'react';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Button,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Alert
} from '@mui/material';
import {
  Person,
  Email,
  Work,
  Security,
  Lock
} from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';

export default function Settings() {
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');
  
  const { user } = useAuth();

  const validatePassword = (password: string): boolean => {
    return password.length >= 8 && 
           /[A-Z]/.test(password) && 
           /\d/.test(password);
  };

  const handlePasswordChange = async () => {
    setPasswordError('');
    
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match');
      return;
    }
    
    if (!validatePassword(newPassword)) {
      setPasswordError('Password must be at least 8 characters with 1 uppercase letter and 1 digit');
      return;
    }
    
    try {
      // Add API call to change password
      setPasswordSuccess('Password changed successfully');
      setPasswordDialogOpen(false);
      setNewPassword('');
      setConfirmPassword('');
    } catch (error) {
      setPasswordError('Failed to change password');
    }
  };

  const getEnvironmentChips = () => {
    if (!user?.environment_access) return null;
    
    return Object.entries(user.environment_access).map(([env, hasAccess]) => (
      <Chip
        key={env}
        label={env.toUpperCase()}
        size="small"
        color={hasAccess ? (env === 'prod' ? 'error' : env === 'qa' ? 'warning' : 'success') : 'default'}
        variant={hasAccess ? 'filled' : 'outlined'}
        sx={{ mr: 0.5, mb: 0.5 }}
      />
    ));
  };

  return (
    <Box sx={{ p: 3, backgroundColor: '#e8f5e8', minHeight: '100vh' }}>
      <Typography variant="h4" gutterBottom color="#2e7d32" fontWeight="bold">
        Settings
      </Typography>

      {passwordSuccess && (
        <Alert severity="success" sx={{ mb: 3 }}>
          {passwordSuccess}
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Profile Information */}
        <Grid item xs={12} md={8}>
          <Card sx={{ borderLeft: '4px solid #4caf50', backgroundColor: '#f1f8e9' }}>
            <CardContent>
              <Typography variant="h6" gutterBottom color="#2e7d32">
                Profile Information
              </Typography>
              
              <List>
                <ListItem>
                  <ListItemIcon>
                    <Person color="primary" sx={{ color: '#4caf50' }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography variant="subtitle1" fontWeight="500" color="#2e7d32">
                        Full Name
                      </Typography>
                    }
                    secondary={
                      <Typography variant="body1" color="text.primary" sx={{ fontFamily: 'Inter, sans-serif' }}>
                        {user?.name}
                      </Typography>
                    }
                  />
                </ListItem>
                
                <ListItem>
                  <ListItemIcon>
                    <Email color="primary" sx={{ color: '#4caf50' }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography variant="subtitle1" fontWeight="500" color="#2e7d32">
                        Email Address
                      </Typography>
                    }
                    secondary={
                      <Typography variant="body1" color="text.primary" sx={{ fontFamily: 'Inter, sans-serif' }}>
                        {user?.email}
                      </Typography>
                    }
                  />
                </ListItem>
                
                <ListItem>
                  <ListItemIcon>
                    <Work color="primary" sx={{ color: '#4caf50' }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography variant="subtitle1" fontWeight="500" color="#2e7d32">
                        Department
                      </Typography>
                    }
                    secondary={
                      <Typography variant="body1" color="text.primary" sx={{ fontFamily: 'Inter, sans-serif' }}>
                        {user?.department}
                      </Typography>
                    }
                  />
                </ListItem>
              </List>
            </CardContent>
          </Card>
        </Grid>

        {/* Environment Access */}
        <Grid item xs={12} md={4}>
          <Card sx={{ borderLeft: '4px solid #66bb6a', backgroundColor: '#e8f5e8' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Security sx={{ mr: 1, color: '#4caf50' }} />
                <Typography variant="h6" color="#2e7d32">Environment Access</Typography>
              </Box>
              
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Current permissions:
              </Typography>
              
              <Box sx={{ mt: 2 }}>
                {getEnvironmentChips()}
              </Box>
              
              <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                Contact your manager to request additional environment access
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Security Settings */}
        <Grid item xs={12}>
          <Card sx={{ borderLeft: '4px solid #81c784', backgroundColor: '#f1f8e9' }}>
            <CardContent>
              <Typography variant="h6" gutterBottom color="#2e7d32">
                Security Settings
              </Typography>
              
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Manage your account security and authentication settings
              </Typography>
              
              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                <Button
                  variant="outlined"
                  startIcon={<Lock />}
                  onClick={() => setPasswordDialogOpen(true)}
                  sx={{ color: '#4caf50', borderColor: '#4caf50' }}
                >
                  Change Password
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Change Password Dialog */}
      <Dialog open={passwordDialogOpen} onClose={() => setPasswordDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Typography variant="h6" color="#2e7d32">Change Password</Typography>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Password Requirements:
          </Typography>
          <Box sx={{ 
            backgroundColor: '#f1f8e9', 
            p: 2, 
            borderRadius: 1, 
            mb: 3,
            border: '1px solid #4caf50'
          }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.8 }}>
              • Minimum 8 characters long<br/>
              • At least 1 uppercase letter (A-Z)<br/>
              • At least 1 digit (0-9)
            </Typography>
          </Box>
          
          {passwordError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {passwordError}
            </Alert>
          )}
          
          <TextField
            fullWidth
            label="New Password"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            sx={{ mb: 2 }}
          />
          
          <TextField
            fullWidth
            label="Confirm New Password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPasswordDialogOpen(false)} color="inherit">
            Cancel
          </Button>
          <Button 
            onClick={handlePasswordChange} 
            variant="contained"
            disabled={!newPassword || !confirmPassword}
            sx={{ backgroundColor: '#4caf50', '&:hover': { backgroundColor: '#388e3c' } }}
          >
            Change Password
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}