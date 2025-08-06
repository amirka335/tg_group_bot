# Telegram Chat History Bot with AI Analysis

A sophisticated Telegram bot that monitors group chats, saves message history to a database, and provides AI-powered analysis using Cerebras API. The bot can generate summaries of recent discussions and answer questions based on chat context.

## Features

- **Real-time Message Storage**: Automatically saves all messages from group chats to a SQLite database
- **AI-Powered Summaries**: Uses Cerebras AI to generate concise summaries of recent chat history
- **Contextual Q&A**: Ask questions about recent discussions and get AI-powered answers based on chat context
- **Flexible Message Limits**: Configure how many recent messages to analyze (1-500 messages)
- **Database Management**: Persistent storage with proper relational structure
- **Markdown Support**: Rich formatting in bot responses using Telegram's MarkdownV2

## Commands

### `/history [n]`
Generate a summary of the last `n` messages in the chat. 
- `n` is optional (default: 100, max: 500)
- Example: `/history 50` - summarizes last 50 messages

### `/qwen [n] [question]`
Ask a question about recent chat history.
- `n` is optional (default: 100, max: 500)
- `question` is your query about the chat context
- Example: `/qwen 50 What was decided about the project deadline?`

## Setup Instructions

### Prerequisites
- Python 3.8+
- Telegram Bot Token (from @BotFather)
- Cerebras API Key (from [Cerebras Cloud](https://cloud.cerebras.ai))

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd telegram-chat-history-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   Create a `.env` file in the project root:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   CEREBRAS_API_KEY=your_cerebras_api_key_here
   ```

4. **Run the bot**
   ```bash
   python bot.py
   ```

## Database Schema

The bot uses SQLite with the following structure:

### Chat Table
- `chat_id` (Primary Key): Telegram chat identifier
- `chat_title`: Name of the chat/group
- `chat_type`: Type of chat (group, supergroup, private, channel)

### ChatMessage Table
- `message_id` (Auto Increment): Unique message identifier
- `chat` (Foreign Key): Reference to Chat table
- `user_id`: Telegram user ID of the sender
- `username`: Telegram username (optional)
- `first_name`: User's first name
- `last_name`: User's last name (optional)
- `text`: Message content
- `date`: Timestamp of the message

## Configuration

### Environment Variables
- `TELEGRAM_BOT_TOKEN`: Required - Your bot token from @BotFather
- `CEREBRAS_API_KEY`: Required - Your API key from Cerebras Cloud

### Bot Settings
- `DEFAULT_MESSAGE_COUNT`: Default number of messages to analyze (100)
- `CEREBRAS_MODEL`: AI model used for analysis (qwen-3-235b-a22b-thinking-2507)

## Usage in Telegram

1. **Add the bot to a group** with admin permissions to read messages
2. **Start the bot** - it will begin saving messages from that point forward
3. **Use commands**:
   - `/history` - Get summary of recent discussions
   - `/qwen What topics were discussed?` - Ask specific questions about chat content

## Development

### Project Structure
```
telegram-chat-history-bot/
├── bot.py              # Main bot application
├── requirements.txt    # Python dependencies
├── .env               # Environment variables (not in git)
├── .gitignore         # Git ignore rules
├── README.md          # This file
└── chat_history.db    # SQLite database (created automatically)
```

### Adding New Features

The bot is built with extensibility in mind. Key areas for enhancement:

1. **New Commands**: Add handlers in the `Command Handlers` section
2. **AI Models**: Modify `CEREBRAS_MODEL` constant to use different models
3. **Database**: Extend models in the `Database Setup` section
4. **Message Processing**: Enhance the `handle_all_text_messages` function

### Error Handling

The bot includes comprehensive error handling:
- Database connection errors
- API failures with fallback responses
- Message parsing issues
- Rate limiting considerations

## Security Considerations

- **Never commit `.env` file** - it contains sensitive API keys
- **Database encryption** - Consider encrypting sensitive chat data
- **Rate limiting** - Implement rate limiting for API calls
- **Input validation** - All user inputs are validated before processing

## Troubleshooting

### Common Issues

1. **Bot not responding**
   - Check if bot token is correct in `.env`
   - Ensure bot has necessary permissions in the group

2. **Database errors**
   - Check file permissions for `chat_history.db`
   - Ensure SQLite is properly installed

3. **AI responses not working**
   - Verify Cerebras API key is valid
   - Check internet connectivity
   - Review logs for API error messages

### Logs
The bot logs all activities to console with timestamps. Check the terminal output for debugging information.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is open source and available under the [MIT License](LICENSE).

## Support

For issues and questions:
- Create an issue in the GitHub repository
- Check existing issues for solutions
- Review the troubleshooting section above
