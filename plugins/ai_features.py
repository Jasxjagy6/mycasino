"""Auto-split from bot.py — plugins.ai_features."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

@check_banned
@check_maintenance
async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)

    # NEW: Check if AI feature is enabled
    if not bot_settings.get("ai_enabled", True):
        await update.message.reply_text(f"{pe('cross')} This feature is currently disabled by the owner.")
        return

    prompt_text = ""
    # Check for reply context
    if update.message.reply_to_message and update.message.reply_to_message.text:
        command_parts = update.message.text.split()
        user_query = ' '.join(command_parts[1:])
        if not user_query: # If just /ai in reply
            user_query = "What do you think about this?"
        prompt_text = f"Considering the context of this message: '{update.message.reply_to_message.text}', respond to the following user query: {user_query}"
    # Check for direct command with prompt
    elif context.args:
        prompt_text = ' '.join(context.args)

    if not prompt_text:
        usage_text = (
            "How can I help you?\n\nUsage:\n"
            "• `/ai your question here`\n"
            "• Reply to a message with `/ai` to discuss it."
        )
        # Use helper bot for usage text in groups
        is_group = update.effective_chat.type in ["group", "supergroup"]
        if is_group and helper_bot:
            try:
                await helper_bot.send_message(chat_id=update.effective_chat.id, text=usage_text)
                return
            except Exception as e:
                logging.warning(f"Helper bot failed for /ai usage: {e}")
        await update.message.reply_text(usage_text)
        return

    # Default to g4f for the direct /ai command
    # In groups, use helper bot for the AI response
    is_group = update.effective_chat.type in ["group", "supergroup"]
    if is_group and helper_bot:
        try:
            status_msg = await helper_bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"{pe('robot')} Thinking with G4f..."
            )
            try:
                ai_response = await g4f.ChatCompletion.create_async(
                    model=g4f.models.default,
                    messages=[{"role": "user", "content": prompt_text}],
                )
                await helper_bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg.message_id,
                    text=ai_response
                )
            except Exception as e:
                logging.error(f"AI (g4f) Error via helper bot: {e}")
                await helper_bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg.message_id,
                    text=f"An error occurred while contacting the AI: {e}"
                )
            return
        except Exception as e:
            logging.warning(f"Helper bot failed for /ai: {e}")

    await process_ai_request(update, prompt_text, "g4f")

async def process_ai_request(update: Update, prompt: str, model_choice: str):
    """Generic function to handle AI requests from different models."""
    status_msg = await update.message.reply_text(f"{pe('robot')} Thinking with {model_choice.title()}...", reply_to_message_id=update.message.message_id)

    try:
        if model_choice == "perplexity": # Updated name
            if PERPLEXITY_API_KEY and PERPLEXITY_API_KEY.startswith("pplx-"):
                client = OpenAI(api_key=PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")
                messages = [{"role": "system", "content": "You are a helpful assistant integrated into a Telegram bot."}, {"role": "user", "content": prompt}]
                response = client.chat.completions.create(model="sonar", messages=messages) # Using a capable model
                ai_response = response.choices[0].message.content
            else:
                ai_response = "Perplexity AI is not configured correctly by the bot owner."

        elif model_choice == "g4f":
            ai_response = await g4f.ChatCompletion.create_async(
                model=g4f.models.default,
                messages=[{"role": "user", "content": prompt}],
            )

        else:
            ai_response = "Invalid AI model selected."

        await status_msg.edit_text(ai_response)

    except Exception as e:
        logging.error(f"AI ({model_choice}) Error: {e}")
        await status_msg.edit_text(f"An error occurred while contacting the AI: {e}")

async def ai_toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle AI assistant feature on/off. Usage: /ai on|off"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(f"{pe('cross')} This is an admin-only command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not context.args or context.args[0].lower() not in ['on', 'off']:
        current_status = "enabled" if bot_settings.get("ai_enabled", True) else "disabled"
        await update.message.reply_text(
            f"{pe('robot')} <b>AI Assistant Feature Status</b>\n\n"
            f"Current: <b>{current_status.upper()}</b>\n\n"
            f"Usage: <code>/ai on</code> or <code>/ai off</code>",
            parse_mode=ParseMode.HTML
        )
        return

    action = context.args[0].lower()
    if action == 'off':
        bot_settings["ai_enabled"] = False
        save_bot_state()
        await update.message.reply_text(f"{pe('check')} AI Assistant feature has been <b>DISABLED</b>. Users will not be able to access AI services.", parse_mode=ParseMode.HTML)
    else:
        bot_settings["ai_enabled"] = True
        save_bot_state()
        await update.message.reply_text(f"{pe('check')} AI Assistant feature has been <b>ENABLED</b>. Users can now access AI services.", parse_mode=ParseMode.HTML)

async def ai_conversation_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    model_choice = context.user_data.get('ai_model')
    if not model_choice:
        await update.message.reply_text("An error occurred. Please start the AI assistant again.")
        context.user_data.clear()
        await start_command(update, context)
        return ConversationHandler.END

    prompt = update.message.text
    await process_ai_request(update, prompt, model_choice)

    # Prompt again for the next question
    await update.message.reply_text(
        "What else can I help you with?",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel & Back to Menu", callback_data="cancel_ai")]])
    )
    return ASK_AI_PROMPT

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('ai', ai_command, block=False))
    app.add_handler(CommandHandler('aioff', ai_toggle_command, block=False))

