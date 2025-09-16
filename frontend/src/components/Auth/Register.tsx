
import { useState, useEffect } from 'react';
import {
  Container,
  Paper,
  TextField,
  Button,
  Typography,
  Box,
  Alert,
  InputAdornment,
  IconButton,
  CircularProgress,
  MenuItem
} from '@mui/material';
import { Visibility, VisibilityOff, Person, Email, Work, SupervisorAccount, Lock, CheckCircle, Cancel } from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import OTPDialog from './OTPDialog';

const departments = [
  'Engineering',
  'DataScience',
  'DevOps',
  'Finance',
  'Marketing',
  'HR'
];

export default function Register() {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    department: '',
    manager_email: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [otpDialogOpen, setOtpDialogOpen] = useState(false);
  const [registerResponse, setRegisterResponse] = useState<any>(null);

  const { register, verifyOTP } = useAuth();
  const navigate = useNavigate();

  const handleChange = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData(prev => ({
      ...prev,
      [field]: e.target.value
    }));
  };

  const validatePassword = (password: string): string => {
    if (password.length < 8) {
      return 'Password must be at least 8 characters';
    }
    if (!/[A-Z]/.test(password)) {
      return 'Password must contain at least one uppercase letter';
    }
    if (!/\d/.test(password)) {
      return 'Password must contain at least one digit';
    }
    return '';
  };

  // Password requirements checker
  const getPasswordRequirements = () => {
    const hasMinLength = formData.password.length >= 8;
    const hasUppercase = /[A-Z]/.test(formData.password);
    const hasDigit = /\d/.test(formData.password);

    return [
      { text: 'At least 8 characters', met: hasMinLength },
      { text: 'One uppercase letter (A-Z)', met: hasUppercase },
      { text: 'One digit (0-9)', met: hasDigit }
    ];
  };

  const getPasswordHelperText = () => {
    if (!formData.password) return '';
    
    const validationError = validatePassword(formData.password);
    if (validationError) return validationError;
    
    return '✓ Password meets all requirements';
  };

  const getPasswordError = () => {
    if (!formData.password) return false;
    return validatePassword(formData.password) !== '';
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    const passwordError = validatePassword(formData.password);
    if (passwordError) {
      setError(passwordError);
      return;
    }
    
    setLoading(true);

    try {
      const response = await register(formData);
      setRegisterResponse(response);
      setOtpDialogOpen(true);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const handleOTPSuccess = () => {
    setOtpDialogOpen(false);
    navigate('/');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <Container maxWidth="sm">
      <Box sx={{ 
        minHeight: '100vh', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        backgroundColor: '#e8f4fd',
        py: 4
      }}>
        <Paper elevation={8} sx={{ 
          p: 4, 
          width: '100%', 
          borderRadius: 3,
          backgroundColor: '#f0f8ff',
          border: '2px solid #1976d2'
        }}>
          <Box sx={{ textAlign: 'center', mb: 4 }}>
            <Typography variant="h4" component="h1" fontWeight="bold" sx={{ color: '#1976d2', mb: 1 }}>
              AiOps Platform
            </Typography>
            <Typography variant="subtitle1" color="text.secondary">
              Infrastructure Management System
            </Typography>
            <Typography variant="h6" sx={{ mt: 3, mb: 2, color: '#424242' }}>
              Sign Up
            </Typography>
          </Box>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <form onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="Full Name"
              value={formData.name}
              onChange={handleChange('name')}
              onKeyPress={handleKeyPress}
              required
              sx={{ 
                mb: 2,
                '& .MuiOutlinedInput-root': {
                  backgroundColor: 'white'
                }
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Person color="action" />
                  </InputAdornment>
                ),
              }}
            />

            <TextField
              fullWidth
              label="Email"
              type="email"
              value={formData.email}
              onChange={handleChange('email')}
              onKeyPress={handleKeyPress}
              required
              sx={{ 
                mb: 2,
                '& .MuiOutlinedInput-root': {
                  backgroundColor: 'white'
                }
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Email color="action" />
                  </InputAdornment>
                ),
              }}
            />

            <TextField
              fullWidth
              label="Password"
              type={showPassword ? 'text' : 'password'}
              value={formData.password}
              onChange={handleChange('password')}
              onKeyPress={handleKeyPress}
              required
              sx={{ 
                mb: 2,
                '& .MuiOutlinedInput-root': {
                  backgroundColor: 'white'
                }
              }}
              helperText={getPasswordHelperText()}
              error={getPasswordError()}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Lock color="action" />
                  </InputAdornment>
                ),
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => setShowPassword(!showPassword)}
                      edge="end"
                    >
                      {showPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />

            {/* Password Requirements Display */}
            {formData.password && (
              <Box sx={{ mb: 2, p: 2, backgroundColor: '#f8f9fa', borderRadius: 1, border: '1px solid #e0e0e0' }}>
                <Typography variant="subtitle2" sx={{ mb: 1, color: '#424242', fontWeight: 600 }}>
                  Password Requirements:
                </Typography>
                {getPasswordRequirements().map((req, index) => (
                  <Box key={index} sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                    {req.met ? (
                      <CheckCircle sx={{ fontSize: 16, color: '#4caf50', mr: 1 }} />
                    ) : (
                      <Cancel sx={{ fontSize: 16, color: '#f44336', mr: 1 }} />
                    )}
                    <Typography 
                      variant="caption" 
                      sx={{ 
                        color: req.met ? '#4caf50' : '#f44336',
                        fontWeight: req.met ? 600 : 400
                      }}
                    >
                      {req.text}
                    </Typography>
                  </Box>
                ))}
              </Box>
            )}

            <TextField
              fullWidth
              select
              label="Department"
              value={formData.department}
              onChange={handleChange('department')}
              onKeyPress={handleKeyPress}
              required
              sx={{ 
                mb: 2,
                '& .MuiOutlinedInput-root': {
                  backgroundColor: 'white'
                }
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Work color="action" />
                  </InputAdornment>
                ),
              }}
            >
              {departments.map((dept) => (
                <MenuItem key={dept} value={dept}>
                  {dept}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              fullWidth
              label="Manager Email"
              type="email"
              value={formData.manager_email}
              onChange={handleChange('manager_email')}
              onKeyPress={handleKeyPress}
              required
              sx={{ 
                mb: 3,
                '& .MuiOutlinedInput-root': {
                  backgroundColor: 'white'
                }
              }}
              helperText="Required for environment access approvals"
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SupervisorAccount color="action" />
                  </InputAdornment>
                ),
              }}
            />

            <Button
              type="submit"
              fullWidth
              variant="contained"
              size="large"
              disabled={loading}
              sx={{ 
                mb: 2, 
                py: 1.5,
                backgroundColor: '#1976d2',
                '&:hover': {
                  backgroundColor: '#1565c0'
                }
              }}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : 'Create Account'}
            </Button>

            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                Already have an account?{' '}
                <Link to="/login" style={{ color: '#1976d2', textDecoration: 'none', fontWeight: 500 }}>
                  Sign In
                </Link>
              </Typography>
            </Box>
          </form>
        </Paper>
      </Box>

      <OTPDialog
        open={otpDialogOpen}
        onClose={() => setOtpDialogOpen(false)}
        email={formData.email}
        onSuccess={handleOTPSuccess}
        message={registerResponse?.message}
      />
    </Container>
  );
}