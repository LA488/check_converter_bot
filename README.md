# 🤖 Telegram Receipt Scanner Bot

Telegram bot for automatic receipt and bank SMS recognition with AI-powered expense categorization and Google Sheets integration.

## 📋 Key Features

- 📸 **Receipt Photo Recognition** - send a receipt photo, bot extracts data via Gemini Vision AI
- 💬 **Bank SMS Parsing** - send SMS text, bot recognizes purchase details
- 🏢 **Company Directory** - automatic matching with known brands database
- ✅ **Data Confirmation** - inline buttons to verify recognized data
- ✏️ **Editing** - ability to correct data before saving
- 📊 **Google Sheets Integration** - automatic expense logging to spreadsheet
- 🔍 **Search** - search by brand, legal entity, category, and subcategory
- 🔄 **Database Sync** - `/reload` command to refresh company directory
- 🚫 **Duplicate Protection** - automatic duplicate entry detection

## 🤖 AI Models

### For Receipt Photo Recognition (vision)
- **Gemini 2.5 Flash** - used for receipt image analysis
- Requires Google AI Studio API key
- Free quota: 1,500 requests per day

### For SMS Text Parsing
- **OpenRouter** - free models with fallback chain:
  1. `google/gemini-flash-1.5` (primary)
  2. `meta-llama/llama-3.2-3b-instruct` (fallback)
  3. `mistralai/mistral-7b-instruct` (fallback)
  4. `qwen/qwen-2-7b-instruct` (fallback)
- Automatic fallback to Gemini when OpenRouter quota exhausted

## 📁 Project Structure

```
├── bot.py                  # Main bot code (aiogram + Flask webhook)
├── mapping_service.py      # Company directory service
├── start.py               # Startup script for Render.com
├── requirements.txt       # Python dependencies
├── render.yaml           # Render.com configuration
├── RENDER_DEPLOY.md      # Detailed deployment guide
├── CHANGELOG.md          # Version history
├── .env.example          # Environment variables template
├── credentials.json      # Google Service Account (not in git)
└── .env                  # Environment variables (not in git)
```

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone <your-repo-url>
cd tg-bot-check-converter
```

### 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create `.env` file based on `.env.example`:

```env
BOT_TOKEN=your_telegram_bot_token
GOOGLE_AI_STUDIO_KEY=your_gemini_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
GOOGLE_SHEET_URL=https://docs.google.com/spreadsheets/d/your_sheet_id
GOOGLE_SERVICE_ACCOUNT_FILE=credentials.json
WEBHOOK_SECRET=random_secret_string_32_chars
```

### 4. Setup Google Sheets

1. Create project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable Google Sheets API
3. Create Service Account and download `credentials.json`
4. Create Google Spreadsheet with two sheets:
   - **Worksheet 0** (expenses): `Brand | Legal Name | Category | Subcategory | Date`
   - **Sheet1** (directory): `ИМЯ | АЛЬФА ИМЯ | КАТЕГОРИЯ | ПОДКАТЕГОРИЯ | Дата`
5. Share spreadsheet with Service Account email

### 5. Get API Keys

- **Telegram Bot Token**: [@BotFather](https://t.me/BotFather) → `/newbot`
- **Gemini API**: [Google AI Studio](https://aistudio.google.com/apikey)
- **OpenRouter API**: [OpenRouter](https://openrouter.ai/keys) (free registration)

### 6. Local Development

```bash
python bot.py
```

Bot starts in polling mode for local development.

## 🌐 Deploy to Render.com (Recommended)

### Why Render.com?
- ✅ Free tier with no external API restrictions
- ✅ Supports all AI services (OpenRouter, Gemini)
- ✅ Automatic deployment from GitHub
- ✅ HTTPS out of the box
- ✅ Webhook mode for Telegram
- ✅ Simple setup via `render.yaml`

### Quick Deploy

1. Sign up at [Render.com](https://render.com)
2. Connect GitHub repository
3. Render auto-detects `render.yaml`
4. Add environment variables in settings
5. Upload `credentials.json` via Secret Files
6. Click Deploy

**Detailed guide**: see [RENDER_DEPLOY.md](RENDER_DEPLOY.md)

### Free Tier
- 750 hours per month (enough for 24/7)
- Auto-sleep after 15 minutes of inactivity
- Cold start ~30 seconds on first request

## 💬 Bot Commands

- `/start` - Main menu and welcome message
- `/help` - Usage instructions
- `/reload` - Refresh brand directory from Google Sheets
- `/cancel` - Cancel current action

## 🔍 Search Modes

- 🔍 **By Brand** - search by commercial name (e.g., "Korzinka")
- 🏢 **By Legal Entity** - search by official name (e.g., "PROWEB MCHJ")
- 📂 **By Category** - search by main category (e.g., "Supermarket")
- 🔹 **By Subcategory** - search by subcategory (e.g., "IT Courses")

## 📊 Data Structure

### Recognized Fields
- **alpha_name** - legal company name (MCHJ, OOO, etc.)
- **brand_name** - commercial brand name
- **category** - main business category (in Russian)
- **subcategory** - business subcategory (in Russian)

### Recognition Example

**Input**: Receipt photo from "PROWEB MCHJ"

**Output**:
```
🏢 Legal Entity: PROWEB MCHJ
🏷 Brand: Proweb
📁 Category: Training Center
🔹 Subcategory: IT Courses
```

## 🛡️ Duplicate Protection

Bot automatically checks for duplicates using:
- Same brand and legal entity
- Time difference less than 5 minutes
- Double-click protection on confirmation button (10 seconds)

## 🔧 Tech Stack

- **Python 3.11+**
- **aiogram 3.x** - async framework for Telegram Bot API
- **Flask** - web server for webhook
- **Gunicorn** - WSGI server for production
- **Google Gemini AI** - image recognition
- **OpenRouter** - text parsing via various LLMs
- **gspread** - Google Sheets integration
- **Pillow** - image processing
- **python-dotenv** - environment management

## 📝 Logging

Bot outputs detailed logs:
- `[GEMINI RECEIPT]` - receipt recognition via Gemini
- `[OPENROUTER SMS]` - SMS parsing via OpenRouter
- `[GEMINI SMS FALLBACK]` - fallback to Gemini for SMS
- `[SAVE]` - Google Sheets save operations
- `[DUPLICATE BLOCKED]` - blocked duplicate entries
- `[CALLBACK]` - inline button handling

## 🐛 Troubleshooting

### Bot Not Responding
1. Check logs on Render.com
2. Verify webhook is set: `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
3. Check `RENDER_DOMAIN` variable

### "Quota Exceeded" Error
- Gemini: 1,500 requests/day, resets at midnight Pacific Time
- OpenRouter: check balance at https://openrouter.ai/credits
- Bot automatically switches to fallback models

### Can't Find credentials.json
1. Ensure file is uploaded via Secret Files in Render
2. Check path in `GOOGLE_SERVICE_ACCOUNT_FILE` variable

### Duplicates in Spreadsheet
- Check date format in "Date" column (should be `YYYY-MM-DD HH:MM`)
- Ensure timezone is UTC+5 (Uzbekistan)

## 📈 Version

**Current Version**: `2.1.0-openrouter`

See [CHANGELOG.md](CHANGELOG.md) for version history.

## 🔗 Useful Links

- [Render Dashboard](https://dashboard.render.com)
- [Render Documentation](https://render.com/docs)
- [OpenRouter](https://openrouter.ai)
- [Google AI Studio](https://aistudio.google.com)
- [aiogram Documentation](https://docs.aiogram.dev)
- [Telegram Bot API](https://core.telegram.org/bots/api)

## 📄 License

MIT License - free to use for personal and commercial projects.

## 🤝 Support

If you have questions or issues:
1. Check [RENDER_DEPLOY.md](RENDER_DEPLOY.md)
2. Review logs on Render.com
3. Check [CHANGELOG.md](CHANGELOG.md) for known issues

---

Made with ❤️ for automated expense tracking
