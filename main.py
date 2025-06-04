await message.channel.send(f"📝 Transcription:\n{text}")

                reply = await correct_grammar(text)
                speech_path = await generate_speech(reply)

                await message.channel.send(f"💬 {reply}")
                await message.channel.send(file=discord.File(speech_path, filename="response.mp3"))
                log_interaction(user_id, "audio_reply", reply)
            except Exception as e:
                await message.channel.send(f"⚠️ Error processing audio: {e}")

    # Text command handling
    if message.content:
        response_text = ""
        try:
            if content.startswith("explain") or "поясни" in content:
                explanation = await explain_correction(message.content)
                response_text = f"📘 Explanation:\n{explanation}"
            elif content.startswith("style") or "стиль" in content:
                improved = await improve_style(message.content)
                response_text = f"🍂 Improved style:\n{improved}"
            elif content.startswith("exercise") or "упражнение" in content:
                topic = message.content.replace("exercise", "").replace("упражнение", "").strip()
                task = await generate_task(topic or "grammar")
                response_text = f"🧩 Exercise on *{topic or 'grammar'}*:\n{task}"
            else:
                corrected = await correct_grammar(message.content)
                response_text = f"✅ Corrected:\n```{corrected}```"
            await message.channel.send(response_text[:2000])
            log_interaction(user_id, "text", response_text)
        except Exception as e:
            await message.channel.send(f"⚠️ Error: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
