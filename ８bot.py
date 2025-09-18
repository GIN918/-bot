import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
from flask import Flask
from threading import Thread
import os
from datetime import datetime

# ===== Flaskサーバー設定 =====
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run).start()

# ===== Discord Bot設定 =====
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

actions = {}

def format_hhmm(time_str: str):
    if len(time_str) == 4:
        return f"{time_str[:2]}:{time_str[2:]}"
    return time_str

# ===== メンション選択プルダウン（昼・夜） =====
class MentionSelect(Select):
    def __init__(self, temp_key: str, label: str):
        self.temp_key = temp_key
        options = [discord.SelectOption(label="@everyone", value="@everyone"),
                   discord.SelectOption(label="@here", value="@here")]
        guilds = bot.guilds
        if guilds:
            for r in guilds[0].roles:
                if not r.is_default():
                    options.append(discord.SelectOption(label=r.name, value=str(r.id)))
        super().__init__(placeholder=label, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if "昼" in self.placeholder:
            actions[self.temp_key]["day_mention"] = self.values[0]
            await interaction.response.send_message(
                "夜のメンションを選択してください",
                view=NightMentionSelectView(self.temp_key),
                ephemeral=True
            )
        else:
            actions[self.temp_key]["night_mention"] = self.values[0]
            await interaction.response.send_modal(TimePeriodModal(self.temp_key))

class DayMentionSelectView(View):
    def __init__(self, temp_key: str):
        super().__init__(timeout=120)
        self.add_item(MentionSelect(temp_key, "昼メンション選択"))

class NightMentionSelectView(View):
    def __init__(self, temp_key: str):
        super().__init__(timeout=120)
        self.add_item(MentionSelect(temp_key, "夜メンション選択"))

# ===== 昼夜時間帯モーダル =====
class TimePeriodModal(Modal, title="昼夜時間帯設定 (HH:MM表示)"):
    def __init__(self, temp_key: str):
        super().__init__()
        self.temp_key = temp_key
        self.day_start = TextInput(label="昼 開始 (HHMM)", placeholder="0900", max_length=4)
        self.day_end = TextInput(label="昼 終了 (HHMM)", placeholder="1759", max_length=4)
        self.night_start = TextInput(label="夜 開始 (HHMM)", placeholder="1800", max_length=4)
        self.night_end = TextInput(label="夜 終了 (HHMM)", placeholder="0859", max_length=4)
        self.add_item(self.day_start)
        self.add_item(self.day_end)
        self.add_item(self.night_start)
        self.add_item(self.night_end)

    async def on_submit(self, interaction: discord.Interaction):
        actions[self.temp_key]["day_start"] = str(self.day_start.value)
        actions[self.temp_key]["day_end"] = str(self.day_end.value)
        actions[self.temp_key]["night_start"] = str(self.night_start.value)
        actions[self.temp_key]["night_end"] = str(self.night_end.value)
        await interaction.response.send_message(
            "監視チャンネルを選択してください（複数選択可）",
            view=WatchChannelSelectView(self.temp_key),
            ephemeral=True
        )

# ===== 監視・返信チャンネル選択 =====
class WatchChannelSelect(Select):
    def __init__(self, temp_key: str):
        self.temp_key = temp_key
        options = [discord.SelectOption(label=ch.name, value=str(ch.id))
                   for ch in bot.get_all_channels() if isinstance(ch, discord.TextChannel)]
        super().__init__(placeholder="監視チャンネルを選択", options=options, min_values=1, max_values=len(options))

    async def callback(self, interaction: discord.Interaction):
        actions[self.temp_key]["watch_channels"] = [int(v) for v in self.values]
        await interaction.response.send_message(
            "返信チャンネルを選択してください（複数選択可）",
            view=ReplyChannelSelectView(self.temp_key),
            ephemeral=True
        )

class ReplyChannelSelect(Select):
    def __init__(self, temp_key: str):
        self.temp_key = temp_key
        options = [discord.SelectOption(label=ch.name, value=str(ch.id))
                   for ch in bot.get_all_channels() if isinstance(ch, discord.TextChannel)]
        super().__init__(placeholder="返信チャンネルを選択", options=options, min_values=1, max_values=len(options))

    async def callback(self, interaction: discord.Interaction):
        actions[self.temp_key]["reply_channels"] = [int(v) for v in self.values]
        await interaction.response.send_modal(MessageModal(self.temp_key))

class WatchChannelSelectView(View):
    def __init__(self, temp_key: str):
        super().__init__(timeout=120)
        self.add_item(WatchChannelSelect(temp_key))

class ReplyChannelSelectView(View):
    def __init__(self, temp_key: str):
        super().__init__(timeout=120)
        self.add_item(ReplyChannelSelect(temp_key))

# ===== 自動返信メッセージ + 登録名モーダル =====
class MessageModal(Modal, title="自動返信メッセージと登録名"):
    def __init__(self, temp_key: str):
        super().__init__()
        self.temp_key = temp_key
        self.message = TextInput(label="返信メッセージ", style=discord.TextStyle.paragraph)
        self.name = TextInput(label="アクション名", style=discord.TextStyle.short)
        self.add_item(self.message)
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        actions[self.temp_key]["message"] = str(self.message.value)
        action_name = str(self.name.value)
        actions[action_name] = actions.pop(self.temp_key)

        guild = interaction.guild
        watch_names = [guild.get_channel(ch_id).name for ch_id in actions[action_name]["watch_channels"]]
        reply_names = [guild.get_channel(ch_id).name for ch_id in actions[action_name]["reply_channels"]]

        desc = (
            f"**監視チャンネル:** {', '.join(watch_names)}\n"
            f"**返信チャンネル:** {', '.join(reply_names)}\n"
            f"**昼メンション:** {actions[action_name].get('day_mention','未設定')}\n"
            f"**夜メンション:** {actions[action_name].get('night_mention','未設定')}\n"
            f"**昼時間:** {format_hhmm(actions[action_name].get('day_start','未設定'))} ～ {format_hhmm(actions[action_name].get('day_end','未設定'))}\n"
            f"**夜時間:** {format_hhmm(actions[action_name].get('night_start','未設定'))} ～ {format_hhmm(actions[action_name].get('night_end','未設定'))}\n"
            f"**メッセージ:** {actions[action_name]['message']}"
        )

        await interaction.response.send_message(
            f"✅ アクション **{action_name}** を登録しました！\n\n{desc}",
            ephemeral=True,
            view=ActionManageView(action_name)
        )

# ===== 登録後の編集 / 削除ビュー =====
class ActionManageView(View):
    def __init__(self, action_name: str):
        super().__init__(timeout=None)
        self.action_name = action_name

        edit_btn = Button(label="編集", style=discord.ButtonStyle.primary)
        edit_btn.callback = self.edit_action
        delete_btn = Button(label="削除", style=discord.ButtonStyle.danger)
        delete_btn.callback = self.delete_action
        self.add_item(edit_btn)
        self.add_item(delete_btn)

    async def edit_action(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"✏️ アクション **{self.action_name}** を再設定してください。",
            ephemeral=True,
            view=DayMentionSelectView(self.action_name)
        )

    async def delete_action(self, interaction: discord.Interaction):
        if self.action_name in actions:
            del actions[self.action_name]
        await interaction.response.send_message(
            f"🗑️ アクション **{self.action_name}** を削除しました。",
            ephemeral=True
        )

# ===== MainSetupView（作成・編集・削除・確認） =====
class MainSetupView(View):
    def __init__(self):
        super().__init__(timeout=None)
        create_btn = Button(label="作成", style=discord.ButtonStyle.success)
        create_btn.callback = self.create_button
        edit_btn = Button(label="編集", style=discord.ButtonStyle.primary)
        edit_btn.callback = self.edit_button
        delete_btn = Button(label="削除", style=discord.ButtonStyle.danger)
        delete_btn.callback = self.delete_button
        check_btn = Button(label="設定確認", style=discord.ButtonStyle.secondary)
        check_btn.callback = self.check_button

        self.add_item(create_btn)
        self.add_item(edit_btn)
        self.add_item(delete_btn)
        self.add_item(check_btn)

    async def create_button(self, interaction: discord.Interaction):
        temp_key = f"temp_{interaction.user.id}_{len(actions)+1}"
        actions[temp_key] = {}
        await interaction.response.send_message(
            "昼のメンションを選択してください",
            view=DayMentionSelectView(temp_key),
            ephemeral=True
        )

    async def edit_button(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "編集するアクションを選択してください",
            view=ActionSelectView(interaction.user.id, "edit"),
            ephemeral=True
        )

    async def delete_button(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "削除するアクションを選択してください",
            view=ActionSelectView(interaction.user.id, "delete"),
            ephemeral=True
        )

    async def check_button(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "確認するアクションを選択してください",
            view=ActionSelectView(interaction.user.id, "check"),
            ephemeral=True
        )

# ===== アクション選択ビュー =====
class ActionSelect(Select):
    def __init__(self, user_id: int, mode: str):
        self.user_id = user_id
        self.mode = mode
        options = [discord.SelectOption(label=name, value=name) for name in actions.keys()]
        super().__init__(placeholder="アクションを選択", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        if self.mode == "edit":
            await interaction.response.send_message(
                f"✏️ アクション **{action_name}** を再設定してください。",
                ephemeral=True,
                view=DayMentionSelectView(action_name)
            )
        elif self.mode == "delete":
            if action_name in actions:
                del actions[action_name]
            await interaction.response.send_message(
                f"🗑️ アクション **{action_name}** を削除しました。",
                ephemeral=True
            )
        elif self.mode == "check":
            data = actions[action_name]
            guild = interaction.guild
            watch_names = [guild.get_channel(ch_id).name for ch_id in data.get("watch_channels", [])]
            reply_names = [guild.get_channel(ch_id).name for ch_id in data.get("reply_channels", [])]
            desc = (
                f"**監視チャンネル:** {', '.join(watch_names)}\n"
                f"**返信チャンネル:** {', '.join(reply_names)}\n"
                f"**昼メンション:** {data.get('day_mention','未設定')}\n"
                f"**夜メンション:** {data.get('night_mention','未設定')}\n"
                f"**昼時間:** {format_hhmm(data.get('day_start','未設定'))} ～ {format_hhmm(data.get('day_end','未設定'))}\n"
                f"**夜時間:** {format_hhmm(data.get('night_start','未設定'))} ～ {format_hhmm(data.get('night_end','未設定'))}\n"
                f"**メッセージ:** {data.get('message','未設定')}"
            )
            await interaction.response.send_message(f"📄 アクション **{action_name}** の設定:\n{desc}", ephemeral=True)

class ActionSelectView(View):
    def __init__(self, user_id: int, mode: str):
        super().__init__(timeout=120)
        self.add_item(ActionSelect(user_id, mode))

# ===== 自動返信処理 =====
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    for name, data in actions.items():
        if message.channel.id in data.get("watch_channels", []):
            now = int(datetime.now().strftime("%H%M"))
            if data["day_start"] <= str(now) <= data["day_end"]:
                mention = data.get("day_mention","")
            else:
                mention = data.get("night_mention","")
            for ch_id in data.get("reply_channels", []):
                ch = bot.get_channel(ch_id)
                if ch:
                    await ch.send(f"{mention}\n{data.get('message','')}")
    await bot.process_commands(message)

# ===== /setup コマンド =====
@bot.tree.command(name="setup", description="セットアップUIを表示")
async def setup(interaction: discord.Interaction):
    await interaction.response.send_message("セットアップUI", view=MainSetupView(), ephemeral=True)

# ===== Bot Token を環境変数から取得 =====
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
bot.run(TOKEN)
