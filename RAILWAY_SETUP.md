# Railway Setup Guide for Burgutali Chat Bot

## Prerequisites
- Railway project created
- Telegram Bot Token from BotFather
- Admin Telegram user ID

## Step 1: Set Environment Variables in Railway

Go to your Railway project dashboard and add these environment variables:

### Required Variables
1. **BOT_TOKEN** (Required)
   - Get this from [@BotFather](https://t.me/botfather) on Telegram
   - Value: `8893922149:AAGZIV4N7y2bHEKGz3ucNK0dvHpF3R3XC8w` (replace with your actual token)
   - **IMPORTANT:** After this update, regenerate your token in BotFather to invalidate the old hardcoded one

2. **CHANNEL_USERNAME** (Optional, defaults to `@burgutali`)
   - The Telegram channel users must subscribe to
   - Include the `@` symbol
   - Example: `@burgutali`

3. **ADMIN_ID** (Optional, defaults to `8904071143`)
   - Your Telegram user ID (numeric only)
   - To find your ID: send `/start` to the bot and check logs

### How to Add Variables in Railway Dashboard:
1. Navigate to your service settings
2. Go to "Variables" tab
3. Add each variable:
   - Click "Add Variable"
   - Enter variable name and value
   - Save

## Step 2: Security - Regenerate Bot Token

⚠️ **The bot token was previously hardcoded in the public GitHub repository. You MUST regenerate it:**

1. Open [@BotFather](https://t.me/botfather)
2. Send `/token`
3. Select your bot
4. Choose `/revoke` to invalidate the old token
5. Copy the new token
6. Update `BOT_TOKEN` in Railway variables with the new token

## Step 3: Deploy to Railway

The service is configured to:
- Pull code from: `hakimbekberdimurodov5107-eng/Burgutali-chat-bot` (main branch)
- Start command: `python bot.py`
- Region: sfo (US West)
- Replicas: 1

### To Deploy:
1. Commit and push changes to GitHub main branch
2. Railway will auto-deploy if auto-deploy is enabled
3. Or manually trigger deployment in Railway dashboard

## Step 4: Verify Deployment

Check the deployment logs in Railway dashboard:
- Look for: `[STARTUP] Bot started successfully`
- Verify: `[STARTUP] Listening for updates...`
- **No Telegram polling conflict errors should appear**

If you see `TelegramConflictError`, it means another bot instance is running:
- Check for local bot instances (`python bot.py` running on your machine)
- Check for multiple Railway deployments
- Regenerate the bot token in BotFather

## Configuration Details

### Database
- File: `bot_database.db`
- Type: SQLite3 with WAL (Write-Ahead Logging) for stability
- Auto-created on first run
- Stores: User registrations (ID, name, username, phone)

### Logging
- Level: INFO
- Format: `timestamp - logger_name - level - message`
- Check Railway logs in dashboard for troubleshooting

## Environment Variables Load Order
1. `.env` file (for local development)
2. Railway environment variables (production)

For local testing:
```bash
cp .env.example .env
# Edit .env with your values
python bot.py
```

## Troubleshooting

### "BOT_TOKEN environment variable is not set"
- Add `BOT_TOKEN` in Railway dashboard variables
- Ensure the value is not empty
- Redeploy after adding

### "Conflict: terminated by other getUpdates request"
- **Multiple bot instances detected**
- Stop any local bot instances
- Check Railway for multiple deployments (delete old ones)
- Regenerate token in BotFather

### Database locked errors
- Database uses WAL (Write-Ahead Logging) for stability
- Check disk space on Railway container
- Restart deployment if issue persists

### Bot not responding to commands
- Verify `BOT_TOKEN` is correct in Railway variables
- Check that bot has received updates in logs
- Verify subscription check: user must be in `CHANNEL_USERNAME`
- For admin commands: verify user ID matches `ADMIN_ID`

## Files Changed

- `bot.py` - Updated to use environment variables and improve error handling
- `requirements.txt` - Added aiohttp explicitly
- `.env.example` - Template for local environment variables
- `.gitignore` - Prevents `.env` and secrets from being committed
- `RAILWAY_SETUP.md` - This file

## Security Best Practices

✅ **Implemented:**
- Bot token loaded from environment variables (not hardcoded)
- `.env` file ignored in git (not committed to repo)
- Proper error handling and logging
- Input sanitization to prevent Markdown injection

⚠️ **Action Items:**
1. Regenerate bot token in BotFather
2. Never hardcode secrets in code or `.env.example`
3. Use Railway's Secrets for sensitive data
4. Regularly audit code for exposed credentials

## Support

For Railway-specific issues: https://docs.railway.app
For Telegram Bot API: https://core.telegram.org/bots/api

