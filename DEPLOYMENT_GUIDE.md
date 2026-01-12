# Deployment Guide for Invoice Extractor

## Key Improvements Made

### 1. Temperature Set to Zero ✅

- Gemini model now uses `temperature=0` for more deterministic and consistent results
- This ensures invoice data extraction is reliable and reproducible

### 2. Session Persistence ✅

- Sessions are now saved to disk in the `sessions/` folder
- Data persists across server restarts
- Fixes the 404 errors when fetching invoice images

### 3. Production Optimizations ✅

- Increased socket timeout to 5 minutes (300 seconds)
- Reduced concurrent workers to 3 (from 8) to prevent API rate limiting
- Added thread-safe session management
- Better error logging for debugging

### 4. Better Error Handling ✅

- Comprehensive logging for all session operations
- Graceful handling of missing sessions
- Better error messages for troubleshooting

## Deployment Steps

### For Production Servers

1. **Environment Variables**
   Create/update your `.env` file:

   ```env
   GEMINI_API_KEY=your_api_key_here
   SECRET_KEY=your-secret-key-here
   FLASK_DEBUG=False
   MAX_INVOICES_PER_SESSION=0
   PORT=8080
   ```

2. **Create Required Folders**

   ```bash
   mkdir uploads
   mkdir sessions
   ```

3. **Use Gunicorn for Production** (Recommended)
   Instead of running with Flask's built-in server, use Gunicorn:

   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:8080 --timeout 300 --graceful-timeout 300 app:app
   ```

   - `-w 4`: 4 worker processes (adjust based on your server)
   - `--timeout 300`: 5-minute timeout for long requests
   - `--graceful-timeout 300`: Allow graceful shutdown

4. **Using systemd (Linux)**
   Create `/etc/systemd/system/invoice-extractor.service`:

   ```ini
   [Unit]
   Description=Invoice Extractor Service
   After=network.target

   [Service]
   User=your_user
   WorkingDirectory=/path/to/invoice matcher
   Environment="PATH=/path/to/venv/bin"
   ExecStart=/path/to/venv/bin/gunicorn -w 4 -b 0.0.0.0:8080 --timeout 300 --graceful-timeout 300 app:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   Then:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start invoice-extractor
   sudo systemctl enable invoice-extractor
   ```

5. **Using Nginx as Reverse Proxy**
   Create nginx config:

   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       client_max_body_size 50M;

       location / {
           proxy_pass http://127.0.0.1:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_connect_timeout 300s;
           proxy_send_timeout 300s;
           proxy_read_timeout 300s;
       }
   }
   ```

## Troubleshooting

### Upload Taking Too Long

- **Cause**: Large PDFs or many pages
- **Solution**:
  - Reduce the number of concurrent files
  - Set `MAX_INVOICES_PER_SESSION` in `.env`
  - Check Gemini API quotas

### "Upload Failed" Errors

- **Cause**: Timeout or API rate limiting
- **Solution**:
  - Check server logs for specific errors
  - Verify GEMINI_API_KEY is valid
  - Ensure network connectivity to Google API
  - Check if you've hit API quota limits

### 404 Errors on Image Fetch

- **Cause**: Session data not persisted
- **Solution**: ✅ Fixed! Sessions now saved to disk
  - Make sure `sessions/` folder exists and is writable
  - Check logs for session save/load errors

### Performance Issues

- Reduce `max_workers` further if needed (edit app.py line 319)
- Increase rate limiter delay (edit line 98)
- Use Redis for session storage in high-traffic scenarios

## Monitoring

Check logs:

```bash
# If using systemd
sudo journalctl -u invoice-extractor -f

# If running directly
tail -f nohup.out
```

## Important Files

- `app.py`: Main application
- `.env`: Configuration
- `sessions/`: Session data storage (gitignored)
- `uploads/`: Temporary file uploads (gitignored)
