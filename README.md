# VideoStreaming App

A self-hosted video streaming platform built with Flask, featuring IP whitelisting, user management, and Netflix-like interface for personal media libraries.

## 🎬 Features

### Core Functionality
- **Video Streaming**: Stream MP4, AVI, MKV, MOV, WMV files
- **Series Management**: Organize videos into TV series with seasons/episodes
- **Auto-thumbnail Generation**: Automatic video thumbnails using OpenCV/MoviePy/PIL
- **User Authentication**: Secure login/registration system
- **Admin Panel**: Comprehensive user and content management

### Security & Access Control
- **IP Whitelisting**: Restrict access to specific IP addresses only
- **Role-based Access**: Admin and regular user permissions
- **Session Management**: Secure user sessions with Flask
- **Access Logging**: Track all login attempts and admin actions

### Content Management
- **Movie Requests**: Users can request new content
- **Upload System**: Admin-only video upload with automatic organization
- **Content Organization**: Automatic series detection and episode ordering
- **Search & Browse**: Easy navigation through movies and series

## 🚀 Quick Start

### Prerequisites
- Python 3.7+
- Flask
- SQLite3
- PIL (Pillow)
- OpenCV (optional, for better thumbnails)
- MoviePy (optional, for better thumbnails)

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd VideoStreaming
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python app.py
   ```

4. **Access the app**
   - Open your browser to `http://localhost:5000`
   - Default admin credentials will be created on first run

### First Time Setup

1. **Initialize Database**
   - Visit `/init-db` to create the initial database structure
   - Or the app will auto-initialize on first run

2. **Configure IP Whitelist**
   - Add your IP address to the whitelist through the admin panel
   - Only whitelisted IPs can access the application

3. **Create Admin User**
   - Register a new user account
   - Use the admin panel to grant admin privileges

## 🏗️ Architecture

### Database Schema
- **users**: User accounts and permissions
- **movies**: Video metadata and file paths
- **series**: TV series organization
- **movie_requests**: User content requests
- **ip_whitelist**: Allowed IP addresses
- **access_logs**: Security and access tracking

### File Structure
```
VideoStreaming/
├── app.py                 # Main Flask application
├── netflix.db            # SQLite database
├── templates/            # HTML templates
├── uploads/             # Video and thumbnail storage
│   ├── videos/         # Video files
│   └── thumbnails/     # Generated thumbnails
└── README.md
```

### Key Components
- **IP Whitelist Middleware**: Blocks all non-whitelisted IPs
- **Thumbnail Generator**: Multi-method thumbnail creation
- **Content Organizer**: Automatic series detection and organization
- **Admin System**: User management and content moderation

## 🔧 Configuration

### Environment Variables
- `SECRET_KEY`: Flask secret key (change in production)
- `UPLOAD_FOLDER`: Video storage directory
- `THUMBNAIL_FOLDER`: Thumbnail storage directory

### IP Whitelist Setup
1. Access admin panel at `/admin`
2. Navigate to IP Whitelist section
3. Add your IP address
4. Remove any test/development IPs

### File Upload Limits
- Supported video formats: MP4, AVI, MKV, MOV, WMV
- Supported image formats: PNG, JPG, JPEG, GIF
- Automatic thumbnail generation for all uploaded videos

## 📱 Usage

### For Users
1. **Browse Content**: View movies and series on the homepage
2. **Watch Videos**: Click on any video to start streaming
3. **Request Content**: Submit requests for new movies/shows
4. **Manage Profile**: Update account information and view history

### For Admins
1. **User Management**: Create, edit, and manage user accounts
2. **Content Upload**: Upload new videos and organize into series
3. **Request Processing**: Approve or deny user content requests
4. **System Monitoring**: View access logs and system statistics
5. **IP Management**: Control access through IP whitelisting

## 🔒 Security Features

### IP Whitelisting
- All routes are protected by IP whitelist
- Automatic blocking of unauthorized IPs
- Detailed logging of access attempts

### User Authentication
- Secure password hashing with Werkzeug
- Session-based authentication
- Admin privilege escalation protection

### Access Control
- Role-based permissions (admin/user)
- Protected admin routes
- Audit logging for all admin actions

## 🐛 Troubleshooting

### Common Issues

**IP Blocked Error**
- Check if your IP is in the whitelist
- Use `/debug-ip` route to see detected IP
- Verify IP address in admin panel

**Thumbnail Generation Fails**
- Install OpenCV: `pip install opencv-python`
- Install MoviePy: `pip install moviepy`
- Check file permissions on upload directories

**Database Errors**
- Visit `/init-db` to recreate database
- Check file permissions on `netflix.db`
- Verify SQLite3 installation

### Debug Routes
- `/debug-ip`: Shows IP detection information
- `/init-db`: Manually initialize database
- `/api/user-count`: Get user statistics (admin only)

## 🚀 Deployment

### Production Considerations
1. **Change Secret Key**: Update `app.secret_key` in `app.py`
2. **Use WSGI Server**: Deploy with Gunicorn or uWSGI
3. **Reverse Proxy**: Use Nginx for SSL termination
4. **Database**: Consider PostgreSQL for larger deployments
5. **File Storage**: Use cloud storage for video files

### Docker Deployment
```bash
# Build and run with Docker
docker build -t videostreaming .
docker run -p 5000:5000 videostreaming
```

## 📊 API Endpoints

### Public Endpoints
- `GET /`: Homepage with featured content
- `GET /login`: Login page
- `GET /register`: Registration page
- `GET /series/<series_name>`: View series episodes

### Protected Endpoints
- `GET /admin`: Admin dashboard (admin only)
- `GET /upload`: Video upload (admin only)
- `GET /admin/users`: User management (admin only)
- `POST /api/user-count`: User statistics (admin only)

### Authentication Required
- `GET /profile`: User profile
- `GET /my-requests`: User's content requests
- `POST /request-movie`: Submit content request

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
1. Check the troubleshooting section
2. Review the debug routes
3. Check the application logs
4. Open an issue on GitHub

---

**Note**: This is a self-hosted application intended for personal or private use. Ensure you have the rights to stream any content you upload. 