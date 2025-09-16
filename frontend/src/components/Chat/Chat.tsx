import { useState, useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  TextField,
  IconButton,
  Typography,
  List,
  ListItem,
  Button,
  Alert,
  CircularProgress,
  Snackbar,
  ButtonGroup
} from '@mui/material';
import {
  Send,
  Refresh,
  SmartToy,
  Person,
  Build
} from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';

interface Message {
  id: string;
  type: 'user' | 'bot' | 'system';
  content: string;
  timestamp: Date;
  buttons?: ButtonOption[];
}

interface ButtonOption {
  text: string;
  value: string;
  variant?: 'contained' | 'outlined';
  color?: 'primary' | 'secondary' | 'success' | 'error';
}

interface PopupNotification {
  id: string;
  title: string;
  message: string;
  type: 'success' | 'error' | 'info' | 'warning';
  duration?: number;
  actionUrl?: string;
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [notifications, setNotifications] = useState<PopupNotification[]>([]);
  const [showTextInput, setShowTextInput] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  const { user } = useAuth();

  useEffect(() => {
    connectWebSocket();
    // Don't add welcome message on load - let it be empty until user starts typing
    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const addWelcomeMessage = () => {
    const welcomeMessage: Message = {
      id: 'welcome',
      type: 'bot',
      content: `Hi ${user?.name}! I am here to help you create and manage infrastructure resources in the cloud. What would you like to deploy today?`,
      timestamp: new Date()
    };
    setMessages([welcomeMessage]);
  };

  const connectWebSocket = () => {
    const token = localStorage.getItem('token');
    if (!token) return;

    const wsUrl = `ws://localhost:8000/ws/chat?token=${token}`;
    const websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      setConnected(true);
    };

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'chat_response') {
        addBotMessage(data.message, data.buttons);
        setProcessing(false);
        setShowTextInput(data.show_text_input !== false);
      } else if (data.type === 'popup_notification') {
        showPopupNotification(data.popup);
      } else if (data.type === 'deployment_complete') {
        handleDeploymentComplete(data);
      }
    };

    websocket.onclose = () => {
      setConnected(false);
      setProcessing(false);
    };

    websocket.onerror = () => {
      setConnected(false);
      setProcessing(false);
      addMessage('system', 'Connection error. Please refresh the page.');
    };

    setWs(websocket);
  };

  const addMessage = (type: 'user' | 'bot' | 'system', content: string, buttons?: ButtonOption[]) => {
    const newMessage: Message = {
      id: Date.now().toString(),
      type,
      content,
      timestamp: new Date(),
      buttons
    };
    setMessages(prev => [...prev, newMessage]);
  };

  const addBotMessage = (content: string, buttons?: ButtonOption[]) => {
    addMessage('bot', content, buttons);
  };

  const sendMessage = (message?: string) => {
    const messageToSend = message || inputValue.trim();
    if (!messageToSend || !ws || !connected) return;

    addMessage('user', messageToSend);
    setProcessing(true);

    ws.send(JSON.stringify({
      type: 'chat_message',
      message: messageToSend,
      timestamp: new Date().toISOString()
    }));

    setInputValue('');
  };

  const handleButtonClick = (value: string, text: string) => {
    sendMessage(value);
  };

  const clearChat = () => {
    if (processing) return;
    
    // Clear messages completely - no system message
    setMessages([]);
    
    // Reset states
    setShowTextInput(true);
    setProcessing(false);
    
    // Send clear signal to backend if connected
    if (ws && connected) {
      ws.send(JSON.stringify({
        type: 'clear_conversation',
        timestamp: new Date().toISOString()
      }));
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const showPopupNotification = (popup: any) => {
    const notification: PopupNotification = {
      id: Date.now().toString(),
      title: popup.title,
      message: popup.message,
      type: popup.type || 'info',
      duration: popup.duration || 5000,
      actionUrl: popup.actionUrl
    };
    
    setNotifications(prev => [...prev, notification]);
    
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== notification.id));
    }, notification.duration);
  };

  const handleDeploymentComplete = (data: any) => {
    const { request_id, details } = data;
    
    showPopupNotification({
      title: 'Infrastructure Deployed!',
      message: `Your infrastructure ${request_id} is ready to use.`,
      type: 'success',
      actionUrl: details.console_url
    });
  };

  const closeNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  const handleNotificationAction = (notification: PopupNotification) => {
    if (notification.actionUrl) {
      window.open(notification.actionUrl, '_blank');
    }
    closeNotification(notification.id);
  };

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', backgroundColor: '#f5f5f5' }}>
      {/* Header */}
      <Box sx={{ 
        p: 2, 
        borderBottom: 1, 
        borderColor: 'divider',
        backgroundColor: '#f5f5f5',
        color: '#424242'
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Build sx={{ color: '#1976d2' }} />
            <Typography variant="h6" color="#424242">AiOps Chat Assistant</Typography>
            {connected ? (
              <Box sx={{ 
                width: 8, 
                height: 8, 
                bgcolor: '#4caf50', 
                borderRadius: '50%',
                ml: 1
              }} />
            ) : (
              <Box sx={{ 
                width: 8, 
                height: 8, 
                bgcolor: '#f44336', 
                borderRadius: '50%',
                ml: 1
              }} />
            )}
          </Box>
          
          <IconButton 
            onClick={clearChat} 
            sx={{ 
              color: '#1565c0',
              backgroundColor: '#e3f2fd',
              '&:hover': {
                backgroundColor: '#bbdefb'
              }
            }}
            disabled={processing}
            title="Clear Chat"
          >
            <Refresh />
          </IconButton>
        </Box>
      </Box>

      {/* Messages Area */}
      <Box sx={{ 
        flexGrow: 1, 
        overflow: 'auto', 
        p: 1,
        backgroundColor: '#ffffff'
      }}>
        <List sx={{ py: 0 }}>
          {messages.map((message) => (
            <ListItem key={message.id} sx={{ py: 1, px: 2, alignItems: 'flex-start' }}>
              <Box sx={{ 
                display: 'flex', 
                width: '100%',
                justifyContent: message.type === 'user' ? 'flex-end' : 'flex-start'
              }}>
                <Box sx={{ maxWidth: '70%' }}>
                  <Paper 
                    elevation={1}
                    sx={{
                      p: 2,
                      backgroundColor: message.type === 'user' 
                        ? '#bbdefb'
                        : message.type === 'system'
                        ? '#e8f5e8'
                        : '#e3f2fd',
                      color: message.type === 'user' ? '#1565c0' : '#424242',
                      borderRadius: message.type === 'user' 
                        ? '18px 18px 4px 18px'
                        : '18px 18px 18px 4px'
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                      {message.type === 'user' ? <Person fontSize="small" /> : 
                       message.type === 'bot' ? <SmartToy fontSize="small" /> : 
                       <Refresh fontSize="small" />}
                      <Typography variant="caption" sx={{ opacity: 0.8, fontWeight: 500 }}>
                        {message.type === 'user' ? user?.name : 
                         message.type === 'bot' ? 'Assistant' : 'System'}
                      </Typography>
                    </Box>
                    
                    <Typography 
                      variant="body1" 
                      sx={{ 
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word'
                      }}
                    >
                      {message.content}
                    </Typography>
                  </Paper>

                  {/* Buttons for bot messages */}
                  {message.buttons && message.buttons.length > 0 && (
                    <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      {message.buttons.map((button, index) => (
                        <Button
                          key={index}
                          variant={button.variant || 'outlined'}
                          color={button.color || 'primary'}
                          onClick={() => handleButtonClick(button.value, button.text)}
                          disabled={processing}
                          sx={{
                            borderRadius: 3,
                            textTransform: 'none',
                            minWidth: 'auto'
                          }}
                        >
                          {button.text}
                        </Button>
                      ))}
                    </Box>
                  )}
                </Box>
              </Box>
            </ListItem>
          ))}
          
          {processing && (
            <ListItem sx={{ py: 1, px: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <SmartToy color="action" />
                <CircularProgress size={20} />
                <Typography variant="body2" color="text.secondary">
                  Processing...
                </Typography>
              </Box>
            </ListItem>
          )}
        </List>
        <div ref={messagesEndRef} />
      </Box>

      {/* Input Area */}
      {showTextInput && (
        <Paper elevation={3} sx={{ p: 2, m: 1, borderRadius: 3, backgroundColor: '#f5f5f5' }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
            <TextField
              fullWidth
              multiline
              minRows={2}
              maxRows={4}
              placeholder="Enter your infrastructure request..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={!connected || processing}
              variant="outlined"
              sx={{
                '& .MuiOutlinedInput-root': {
                  borderRadius: 2,
                  backgroundColor: 'white',
                  fontSize: '16px',
                  '& fieldset': {
                    borderColor: '#ddd'
                  },
                  '&:hover fieldset': {
                    borderColor: '#bbb'
                  },
                  '&.Mui-focused fieldset': {
                    borderColor: '#888'
                  }
                }
              }}
            />
            <IconButton
              onClick={() => sendMessage()}
              disabled={!inputValue.trim() || !connected || processing}
              sx={{
                backgroundColor: '#424242',
                color: 'white',
                width: 48,
                height: 48,
                '&:hover': {
                  backgroundColor: '#333',
                },
                '&:disabled': {
                  backgroundColor: '#e0e0e0',
                  color: '#9e9e9e'
                }
              }}
            >
              <Send />
            </IconButton>
          </Box>
          
          {!connected && (
            <Alert severity="warning" sx={{ mt: 1 }}>
              Not connected to chat service. Please refresh the page.
            </Alert>
          )}
        </Paper>
      )}

      {/* Popup Notifications */}
      {notifications.map((notification, index) => (
        <Snackbar
          key={notification.id}
          open={true}
          anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
          sx={{ mt: 8 + (index * 80) }}
        >
          <Alert
            severity={notification.type}
            onClose={() => closeNotification(notification.id)}
            action={
              notification.actionUrl && (
                <Button
                  color="inherit"
                  size="small"
                  onClick={() => handleNotificationAction(notification)}
                >
                  ACCESS
                </Button>
              )
            }
          >
            <Typography variant="subtitle2">{notification.title}</Typography>
            <Typography variant="body2">{notification.message}</Typography>
          </Alert>
        </Snackbar>
      ))}
    </Box>
  );
}