import asyncio
import html
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import config
import database as db
import bracket

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


class RegisterStates(StatesGroup):
    waiting_for_nickname = State()


class NewTournamentStates(StatesGroup):
    waiting_for_name = State()


class AnnounceChannelStates(StatesGroup):
    waiting_for_text = State()


BTN_REGISTER = "📝 Зарегистрироваться"
BTN_UNREGISTER = "🚪 Отменить регистрацию"
BTN_PARTICIPANTS = "👥 Участники"
BTN_BRACKET = "📋 Сетка"
BTN_MY_STATS = "📊 Моя статистика"

BTN_NEW_TOURNAMENT = "🆕 Новый турнир"
BTN_START_BRACKET = "▶️ Начать сетку"
BTN_FORCE_READY = "⏩ Ускорить проверку готовности"
BTN_END_TOURNAMENT = "🛑 Завершить турнир"
BTN_ANNOUNCE_CHANNEL = "📢 Объявление в канал"


async def user_panel_keyboard(chat_id: int, selective: bool = False) -> ReplyKeyboardMarkup:
    tournament = await db.get_active_tournament(chat_id)
    rows = []
    if tournament:
        if tournament["status"] == "registration":
            rows.append([KeyboardButton(text=BTN_REGISTER), KeyboardButton(text=BTN_UNREGISTER)])
        rows.append([KeyboardButton(text=BTN_PARTICIPANTS), KeyboardButton(text=BTN_BRACKET)])
    rows.append([KeyboardButton(text=BTN_MY_STATS)])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        selective=selective,
        input_field_placeholder="Выберите действие",
    )


async def admin_panel_keyboard(chat_id: int, selective: bool = False) -> ReplyKeyboardMarkup:
    tournament = await db.get_active_tournament(chat_id)
    rows = []
    if tournament:
        if tournament["status"] == "registration":
            rows.append([KeyboardButton(text=BTN_REGISTER), KeyboardButton(text=BTN_UNREGISTER)])
        rows.append([KeyboardButton(text=BTN_PARTICIPANTS), KeyboardButton(text=BTN_BRACKET)])
    rows.append([KeyboardButton(text=BTN_MY_STATS)])

    if not tournament:
        rows.append([KeyboardButton(text=BTN_NEW_TOURNAMENT)])
    else:
        if tournament["status"] == "registration":
            rows.append([KeyboardButton(text=BTN_START_BRACKET)])
        if tournament["status"] in ("checking_readiness", "in_progress"):
            rows.append([KeyboardButton(text=BTN_FORCE_READY)])
        rows.append([KeyboardButton(text=BTN_END_TOURNAMENT)])
    rows.append([KeyboardButton(text=BTN_ANNOUNCE_CHANNEL)])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        selective=selective,
        input_field_placeholder="Выберите действие или введите команду",
    )


async def refresh_admin_keyboard(message: Message) -> None:
    try:
        await message.reply(
            "🔄 Панель обновлена.",
            reply_markup=await admin_panel_keyboard(message.chat.id, selective=True),
        )
    except Exception:
        logging.info("Не удалось обновить клавиатуру админ-панели")


@dp.message(Command("admin"))
async def cmd_admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только админам турнира.")
        return
    await message.answer(
        "🛠 <b>Админ-панель</b>\nВыберите действие кнопкой внизу экрана.",
        parse_mode="HTML",
        reply_markup=await admin_panel_keyboard(message.chat.id),
    )


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    if is_admin(message.from_user.id):
        await message.answer("🛠 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=await admin_panel_keyboard(message.chat.id))
    else:
        await message.answer("📱 <b>Меню</b>", parse_mode="HTML", reply_markup=await user_panel_keyboard(message.chat.id))


@dp.message(F.text == BTN_NEW_TOURNAMENT)
async def panel_new_tournament(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    active = await db.get_active_tournament(message.chat.id)
    if active:
        await message.answer(
            f"В этом чате уже есть активный турнир: «{active['name']}» "
            f"(статус: {active['status']}). Сначала завершите его."
        )
        return
    await state.set_state(NewTournamentStates.waiting_for_name)
    await message.answer("Введите название турнира:")


@dp.message(F.text == BTN_START_BRACKET)
async def panel_start_bracket(message: Message):
    if not is_admin(message.from_user.id):
        return
    await cmd_start_bracket(message)


@dp.message(F.text == BTN_PARTICIPANTS)
async def panel_participants(message: Message):
    await cmd_participants(message)


@dp.message(F.text == BTN_BRACKET)
async def panel_bracket(message: Message):
    await cmd_bracket(message)


@dp.message(F.text == BTN_REGISTER)
async def panel_register(message: Message, state: FSMContext):
    tournament = await db.get_active_tournament(message.chat.id)
    if not tournament:
        await message.answer("Сейчас нет активного турнира. Дождитесь /new_tournament от админа.")
        return
    if tournament["status"] != "registration":
        await message.answer("Регистрация на этот турнир уже закрыта.")
        return
    await state.set_state(RegisterStates.waiting_for_nickname)
    await state.update_data(tournament_id=tournament["id"])
    await message.answer("Введите ваш ник в Clash Royale, под которым вы будете участвовать в турнире:")


@dp.message(F.text == BTN_UNREGISTER)
async def panel_unregister(message: Message):
    await cmd_unregister(message)


@dp.message(F.text == BTN_MY_STATS)
async def panel_my_stats(message: Message):
    await cmd_my_stats(message)


@dp.message(F.text == BTN_FORCE_READY)
async def panel_force_ready(message: Message):
    if not is_admin(message.from_user.id):
        return
    await cmd_force_ready_check(message)


@dp.message(F.text == BTN_END_TOURNAMENT)
async def panel_end_tournament(message: Message):
    if not is_admin(message.from_user.id):
        return
    await cmd_end_tournament(message)


@dp.message(F.text == BTN_ANNOUNCE_CHANNEL)
async def panel_announce_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not config.CHANNEL_USERNAME:
        await message.answer(
            "В config.py не задан CHANNEL_USERNAME — некуда публиковать объявление."
        )
        return
    await state.set_state(AnnounceChannelStates.waiting_for_text)
    await message.answer(f"Введите текст объявления для канала {config.CHANNEL_USERNAME}:")


@dp.message(AnnounceChannelStates.waiting_for_text)
async def process_announce_channel_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.clear()
    if not text:
        await message.answer("Текст не может быть пустым. Нажмите кнопку ещё раз, чтобы попробовать снова.")
        return

    open_tournament = await db.get_latest_open_tournament()
    keyboard = None
    if open_tournament:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📝 Зарегистрироваться",
                url=f"https://t.me/{config.BOT_USERNAME}?start=register",
            )
        ]])

    try:
        await bot.send_message(config.CHANNEL_USERNAME, text, reply_markup=keyboard)
        note = "" if open_tournament else "\n\nℹ️ Нет турнира с открытой регистрацией — кнопку не добавил."
        await message.answer("✅ Объявление опубликовано в канале." + note)
    except Exception as e:
        await message.answer(
            f"Не удалось опубликовать в канал: {e}\n\n"
            "Проверьте: бот добавлен в канал как администратор с правом публикации сообщений."
        )


async def nick(participant_id: int | None, escape: bool = True) -> str:
    if participant_id is None:
        return "—"
    p = await db.get_participant(participant_id)
    raw = p["nickname"] if p else "неизвестный игрок"
    return html.escape(raw) if escape else raw


class _ChatIdHolder:
    def __init__(self, chat_id: int):
        self.id = chat_id


class ChatTarget:

    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.chat = _ChatIdHolder(chat_id)

    async def answer(self, text: str, parse_mode: str | None = None, reply_markup=None):
        return await bot.send_message(self.chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)


# таймеры проверок готовности, чтобы можно было снять их раньше
pending_pre_bracket_tasks: dict[int, asyncio.Task] = {}
pending_match_tasks: dict[int, asyncio.Task] = {}

# без лока два одновременных «Готов» могут не увидеть друг друга
readiness_lock = asyncio.Lock()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Зарегистрироваться", callback_data="menu_register")],
        [InlineKeyboardButton(text="👥 Участники", callback_data="menu_participants")],
        [InlineKeyboardButton(text="📋 Сетка", callback_data="menu_bracket")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="menu_my_stats")],
    ])


STATUS_LABELS = {
    "registration": "🟢 регистрация открыта",
    "checking_readiness": "⏳ проверка готовности участников",
    "in_progress": "▶️ сетка в разгаре",
}


async def build_welcome_text(message: Message) -> str:
    name = html.escape(message.from_user.first_name or "боец")
    lines = [f"🏆 Привет, {name}! Это бот турниров Clash Royale."]

    tournament = await db.get_active_tournament(message.chat.id)
    if not tournament:
        lines.append("\nСейчас активного турнира нет — загляните позже.")
    else:
        participants = await db.get_participants(tournament["id"])
        count_label = (
            f"{len(participants)}/{config.MAX_PARTICIPANTS}"
            if config.MAX_PARTICIPANTS > 0
            else str(len(participants))
        )
        status_label = STATUS_LABELS.get(tournament["status"], tournament["status"])
        lines.append(f"\n🎮 Турнир: <b>{html.escape(tournament['name'])}</b>")
        lines.append(f"Статус: {status_label}")
        lines.append(f"Участников: {count_label}")
        if tournament["status"] == "in_progress":
            max_round = await db.get_max_round(tournament["id"])
            lines.append(f"Текущий раунд: {max_round}")

    lines.append("\n👇 Пользуйтесь кнопками меню внизу экрана.")
    return "\n".join(lines)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = HELP_TEXT_USER + (HELP_TEXT_ADMIN if is_admin(message.from_user.id) else "")
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard())
    if is_admin(message.from_user.id):
        await message.answer("🛠 Админ-панель:", reply_markup=await admin_panel_keyboard(message.chat.id))
    else:
        await message.answer("📱 Меню:", reply_markup=await user_panel_keyboard(message.chat.id))


@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    # пришли по кнопке из поста в канале (t.me/бот?start=register)
    if command.args == "register":
        tournament = await db.get_latest_open_tournament()
        if not tournament:
            await message.answer("Сейчас нет турнира с открытой регистрацией. Загляните позже.")
            return
        await state.set_state(RegisterStates.waiting_for_nickname)
        await state.update_data(tournament_id=tournament["id"])
        await message.answer(
            f"🎮 Регистрация на турнир «{tournament['name']}»!\n"
            "Введите ваш ник в Clash Royale:"
        )
        return

    await message.answer(await build_welcome_text(message), parse_mode="HTML")
    if is_admin(message.from_user.id):
        await message.answer(
            "🛠 Админ-панель активна — пользуйтесь кнопками внизу экрана.",
            reply_markup=await admin_panel_keyboard(message.chat.id),
        )
    else:
        await message.answer(
            "📱 Меню активно — пользуйтесь кнопками внизу экрана.",
            reply_markup=await user_panel_keyboard(message.chat.id),
        )


HELP_TEXT_USER = (
    "🏆 <b>Бот турниров Clash Royale</b>\n\n"
    "/register — зарегистрироваться (бот спросит ваш ник в Clash Royale)\n"
    "/unregister — отменить свою регистрацию (пока не закрыт набор)\n"
    "/participants — список участников\n"
    "/bracket — текущая турнирная сетка\n"
    "/my_stats — ваша личная статистика по всем турнирам\n"
    "/lobby &lt;id_матча&gt; &lt;ссылка&gt; — прислать ссылку на приватный "
    "Дружеский бой в Clash Royale, чтобы бот переслал её сопернику\n"
    "/menu — заново открыть меню с кнопками внизу экрана, если оно пропало "
    "(обычно появляется само после /start)\n\n"
    "⏳ Перед стартом турнира и перед каждым раундом бот попросит подтвердить "
    "готовность кнопкой. Не успели вовремя — перед сеткой вас снимут с турнира, "
    "а перед матчем засчитают техническое поражение.\n"
)

HELP_TEXT_ADMIN = (
    "\n<b>Для админов:</b>\n"
    "/admin — заново открыть панель с кнопками внизу экрана, если она пропала "
    "(обычно появляется сама после /start)\n"
    "/new_tournament — создать турнир (бот спросит название) и открыть регистрацию\n"
    "/start_bracket — закрыть регистрацию и запустить проверку готовности "
    "участников (по её завершении сформируется сетка)\n"
    "/result &lt;id_матча&gt; &lt;1|2&gt; — внести результат матча вручную, "
    "если кнопка под матчем потерялась\n"
    "/force_ready_check — не ждать таймаут и сразу завершить текущую проверку "
    "готовности (например, после перезапуска бота)\n"
    "/end_tournament — завершить турнир досрочно (на любом этапе)\n"
    "/announce_channel &lt;@канал&gt; &lt;текст&gt; — опубликовать пост с кнопкой "
    "регистрации в канале\n"
)


@dp.message(Command("new_tournament"))
async def cmd_new_tournament(message: Message, command: CommandObject, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только админам турнира.")
        return

    name = (command.args or "").strip()
    if name:
        await finish_new_tournament(message, name)
    else:
        await state.set_state(NewTournamentStates.waiting_for_name)
        await message.answer("Введите название турнира:")


@dp.message(NewTournamentStates.waiting_for_name)
async def process_new_tournament_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    await state.clear()

    if not name:
        await message.answer("Название не может быть пустым. Отправьте /new_tournament ещё раз.")
        return

    await finish_new_tournament(message, name)


async def finish_new_tournament(message: Message, name: str):
    active = await db.get_active_tournament(message.chat.id)
    if active:
        await message.answer(
            f"В этом чате уже есть активный турнир: «{active['name']}» "
            f"(статус: {active['status']}). Сначала завершите его."
        )
        return

    tid = await db.create_tournament(message.chat.id, name)
    await message.answer(
        f"🎮 Турнир «{name}» создан! Регистрация открыта.\n"
        f"Чтобы участвовать, отправьте: /register <ваш ник>"
    )
    await announce_tournament_start_to_channel(name)
    if is_admin(message.from_user.id):
        await refresh_admin_keyboard(message)


@dp.message(Command("register"))
async def cmd_register(message: Message, command: CommandObject, state: FSMContext):
    tournament = await db.get_active_tournament(message.chat.id)
    if not tournament:
        await message.answer("Сейчас нет активного турнира. Дождитесь /new_tournament от админа.")
        return
    if tournament["status"] != "registration":
        await message.answer("Регистрация на этот турнир уже закрыта.")
        return

    nickname = (command.args or "").strip()
    if nickname:
        await finish_registration(message, tournament, nickname)
    else:
        await state.set_state(RegisterStates.waiting_for_nickname)
        await state.update_data(tournament_id=tournament["id"])
        await message.answer("Введите ваш ник в Clash Royale, под которым вы будете участвовать в турнире:")


@dp.message(RegisterStates.waiting_for_nickname)
async def process_nickname_reply(message: Message, state: FSMContext):
    nickname = (message.text or "").strip()
    data = await state.get_data()
    await state.clear()

    if not nickname:
        await message.answer("Ник не может быть пустым. Отправьте /register ещё раз.")
        return

    tournament = await db.get_tournament(data["tournament_id"])
    if not tournament or tournament["status"] != "registration":
        await message.answer("Регистрация на турнир уже закрыта.")
        return

    await finish_registration(message, tournament, nickname)


async def finish_registration(message: Message, tournament, nickname: str):
    if config.MAX_PARTICIPANTS > 0:
        current = await db.get_participants(tournament["id"])
        if len(current) >= config.MAX_PARTICIPANTS:
            await message.answer(
                f"😔 Достигнут лимит участников турнира ({config.MAX_PARTICIPANTS}). "
                "Регистрация закрыта."
            )
            return

    added = await db.add_participant(
        tournament["id"], message.from_user.id, message.from_user.username, nickname
    )
    if added:
        await message.answer(
            f"✅ Ник «{nickname}» зарегистрирован на турнир «{tournament['name']}»!\n"
            "Если передумаете — можно отменить регистрацию командой /unregister."
        )
    else:
        await message.answer("Вы уже зарегистрированы на этот турнир.")


@dp.message(Command("unregister"))
async def cmd_unregister(message: Message):
    tournament = await db.get_active_tournament(message.chat.id)
    if not tournament:
        await message.answer("Сейчас нет активного турнира.")
        return
    if tournament["status"] != "registration":
        await message.answer("Регистрация уже закрыта, отменить участие нельзя.")
        return

    removed = await db.remove_participant(tournament["id"], message.from_user.id)
    if removed:
        await message.answer("Регистрация отменена. Если передумаете — /register снова открыт.")
    else:
        await message.answer("Вы не были зарегистрированы на этот турнир.")


@dp.message(Command("participants"))
async def cmd_participants(message: Message):
    tournament = await db.get_active_tournament(message.chat.id)
    if not tournament:
        await message.answer("Сейчас нет активного турнира.")
        return

    participants = await db.get_participants(tournament["id"])
    if not participants:
        await message.answer("Пока никто не зарегистрировался.")
        return

    count_label = (
        f"{len(participants)}/{config.MAX_PARTICIPANTS}"
        if config.MAX_PARTICIPANTS > 0
        else str(len(participants))
    )
    lines = [f"{i+1}. {p['nickname']}" for i, p in enumerate(participants)]
    await message.answer(
        f"👥 Участники турнира «{tournament['name']}» ({count_label}):\n" + "\n".join(lines)
    )


def format_stats_text(stats: dict) -> str:
    lines = [
        "📊 <b>Ваша статистика</b>",
        f"Турниров сыграно: {stats['tournaments_played']}",
        f"🏆 Побед в турнирах: {stats['championships']}",
        f"Матчей сыграно: {stats['matches_played']}",
        f"Побед: {stats['wins']}",
        f"Поражений: {stats['losses']}",
    ]
    return "\n".join(lines)


@dp.message(Command("my_stats"))
async def cmd_my_stats(message: Message):
    stats = await db.get_user_stats(message.from_user.id)
    if stats["tournaments_played"] == 0:
        await message.answer("Вы ещё не участвовали ни в одном турнире.")
        return
    await message.answer(format_stats_text(stats), parse_mode="HTML")


@dp.callback_query(F.data == "menu_register")
async def cb_menu_register(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tournament = await db.get_active_tournament(callback.message.chat.id)
    if not tournament:
        await callback.message.answer("Сейчас нет активного турнира. Дождитесь /new_tournament от админа.")
        return
    if tournament["status"] != "registration":
        await callback.message.answer("Регистрация на этот турнир уже закрыта.")
        return
    await state.set_state(RegisterStates.waiting_for_nickname)
    await state.update_data(tournament_id=tournament["id"])
    await callback.message.answer("Введите ваш ник в Clash Royale, под которым вы будете участвовать в турнире:")


@dp.callback_query(F.data == "menu_participants")
async def cb_menu_participants(callback: CallbackQuery):
    await callback.answer()
    await cmd_participants(callback.message)


@dp.callback_query(F.data == "menu_bracket")
async def cb_menu_bracket(callback: CallbackQuery):
    await callback.answer()
    await cmd_bracket(callback.message)


@dp.callback_query(F.data == "menu_my_stats")
async def cb_menu_my_stats(callback: CallbackQuery):
    await callback.answer()
    stats = await db.get_user_stats(callback.from_user.id)
    if stats["tournaments_played"] == 0:
        await callback.message.answer("Вы ещё не участвовали ни в одном турнире.")
        return
    await callback.message.answer(format_stats_text(stats), parse_mode="HTML")


@dp.message(Command("start_bracket"))
async def cmd_start_bracket(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только админам турнира.")
        return

    tournament = await db.get_active_tournament(message.chat.id)
    if not tournament:
        await message.answer("Сейчас нет активного турнира.")
        return
    if tournament["status"] != "registration":
        await message.answer("Сетка уже сформирована для этого турнира (или идёт проверка готовности).")
        return

    participants = await db.get_participants(tournament["id"])
    if len(participants) < 2:
        await message.answer("Нужно минимум 2 участника, чтобы сформировать сетку.")
        return

    if config.READINESS_TIMEOUT_MINUTES <= 0:
        await build_bracket_now(tournament["id"], message)
        await refresh_admin_keyboard(message)
        return

    await start_pre_bracket_readiness_check(tournament["id"], message, participants)
    await refresh_admin_keyboard(message)


async def build_bracket_now(tournament_id: int, chat):
    participants = await db.get_participants(tournament_id)
    participant_ids = [p["id"] for p in participants]
    pairs, bye_players = bracket.shuffle_and_build_round1(participant_ids)

    matches = []
    position = 0
    for pid in bye_players:
        matches.append(
            {"position": position, "player1_id": pid, "player2_id": None,
             "winner_id": pid, "status": "bye"}
        )
        position += 1
    for p1, p2 in pairs:
        matches.append(
            {"position": position, "player1_id": p1, "player2_id": p2,
             "winner_id": None, "status": "pending"}
        )
        position += 1

    await db.create_matches(tournament_id, 1, matches)
    await db.set_tournament_status(tournament_id, "in_progress")

    await announce_round(chat, tournament_id, 1)

    # вдруг в первом раунде одни баи
    await advance_if_round_complete(chat, tournament_id, 1)


async def start_pre_bracket_readiness_check(tournament_id: int, message, participants):
    participant_ids = [p["id"] for p in participants]
    await db.create_readiness_checks(tournament_id, None, participant_ids)
    await db.set_tournament_status(tournament_id, "checking_readiness")

    names = ", ".join(html.escape(p["nickname"]) for p in participants)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Я готов", callback_data=f"readypre:{tournament_id}")
    ]])
    await message.answer(
        "⏳ <b>Подтвердите готовность к началу турнира!</b>\n"
        f"Участники: {names}\n\n"
        f"У вас есть {config.READINESS_TIMEOUT_MINUTES} мин., чтобы нажать кнопку ниже "
        "(или кнопку в личном сообщении от бота, если он вам её прислал). "
        "Не успевшие подтвердить будут сняты с турнира.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    # кто зарегался через канал, чат не видит — дублируем кнопку в личку
    for p in participants:
        personal_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Я готов", callback_data=f"readypre:{tournament_id}")
        ]])
        try:
            await bot.send_message(
                p["user_id"],
                "⏳ Подтвердите готовность к началу турнира!\n"
                f"У вас есть {config.READINESS_TIMEOUT_MINUTES} мин., иначе вы будете "
                "сняты с турнира.",
                reply_markup=personal_keyboard,
            )
        except Exception:
            logging.info(
                f"Не удалось отправить личную проверку готовности участнику user_id={p['user_id']}"
            )

    task = asyncio.create_task(
        resolve_pre_bracket_readiness(
            tournament_id, message.chat.id, config.READINESS_TIMEOUT_MINUTES * 60
        )
    )
    pending_pre_bracket_tasks[tournament_id] = task


async def resolve_pre_bracket_readiness(tournament_id: int, chat_id: int, timeout_seconds: float):
    try:
        await asyncio.sleep(timeout_seconds)
    except asyncio.CancelledError:
        return
    await resolve_pre_bracket_readiness_now(tournament_id, chat_id)


async def resolve_pre_bracket_readiness_now(tournament_id: int, chat_id: int):
    pending_pre_bracket_tasks.pop(tournament_id, None)

    tournament = await db.get_tournament(tournament_id)
    if not tournament or tournament["status"] != "checking_readiness":
        return

    chat = ChatTarget(chat_id)
    checks = await db.get_pre_bracket_checks(tournament_id)
    not_ready_names = []
    for c in checks:
        if not c["confirmed"]:
            p = await db.get_participant(c["participant_id"])
            if p:
                not_ready_names.append(p["nickname"])
                await db.remove_participant(tournament_id, p["user_id"])

    if not_ready_names:
        await chat.answer(
            "❌ Не подтвердили готовность и сняты с турнира: "
            + ", ".join(html.escape(n) for n in not_ready_names),
            parse_mode="HTML",
        )

    remaining = await db.get_participants(tournament_id)
    if len(remaining) < 2:
        await db.set_tournament_status(tournament_id, "finished")
        await chat.answer("🛑 Готовых участников осталось меньше 2 — турнир отменён.")
        await announce_tournament_cancelled_to_channel(tournament["name"])
        return

    await build_bracket_now(tournament_id, chat)


@dp.callback_query(F.data.startswith("readypre:"))
async def cb_ready_pre(callback: CallbackQuery):
    tournament_id = int(callback.data.split(":")[1])
    tournament = await db.get_tournament(tournament_id)
    if not tournament or tournament["status"] != "checking_readiness":
        await callback.answer("Проверка готовности уже завершена.", show_alert=True)
        return

    participant = await db.get_participant_by_user(tournament_id, callback.from_user.id)
    if not participant:
        await callback.answer("Вы не зарегистрированы на этот турнир.", show_alert=True)
        return

    async with readiness_lock:
        checks = await db.get_pre_bracket_checks(tournament_id)
        my_check = next((c for c in checks if c["participant_id"] == participant["id"]), None)
        if not my_check:
            await callback.answer("Проверка готовности не найдена.", show_alert=True)
            return

        already = bool(my_check["confirmed"])
        await db.confirm_readiness(my_check["id"])
        checks = await db.get_pre_bracket_checks(tournament_id)
        all_confirmed = all(c["confirmed"] for c in checks)

    await callback.answer("Готовность уже была подтверждена ранее." if already else "✅ Готовность подтверждена!")

    if all_confirmed:
        task = pending_pre_bracket_tasks.pop(tournament_id, None)
        if task:
            task.cancel()
        chat = ChatTarget(tournament["chat_id"])
        await chat.answer("🎉 Все участники подтвердили готовность! Формируем сетку...")
        await resolve_pre_bracket_readiness_now(tournament_id, tournament["chat_id"])


@dp.message(Command("force_ready_check"))
async def cmd_force_ready_check(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только админам турнира.")
        return

    tournament = await db.get_active_tournament(message.chat.id)
    if not tournament:
        await message.answer("Сейчас нет активного турнира в этом чате.")
        return

    if tournament["status"] == "checking_readiness":
        task = pending_pre_bracket_tasks.pop(tournament["id"], None)
        if task:
            task.cancel()
        await message.answer("⏩ Проверка готовности к сетке завершена принудительно.")
        await resolve_pre_bracket_readiness_now(tournament["id"], message.chat.id)
        return

    max_round = await db.get_max_round(tournament["id"])
    pending_matches = []
    if max_round:
        matches = await db.get_matches(tournament["id"], max_round)
        pending_matches = [m for m in matches if m["status"] == "pending"]

    resolved_any = False
    for m in pending_matches:
        checks = await db.get_readiness_checks_for_match(m["id"])
        if not checks:
            continue
        task = pending_match_tasks.pop(m["id"], None)
        if task:
            task.cancel()
        await resolve_match_readiness_now(m["id"], message.chat.id)
        resolved_any = True

    if resolved_any:
        await message.answer("⏩ Проверки готовности текущего раунда завершены принудительно.")
    else:
        await message.answer("Сейчас нет ни одной проверки готовности, ожидающей решения.")


async def notify_player_of_match(participant_row, opponent_name: str, match_id: int, round_num: int):
    if not participant_row:
        return
    text = (
        f"🥊 Раунд {round_num}: начался ваш матч #{match_id}!\n"
        f"Соперник: <b>{html.escape(opponent_name)}</b>\n\n"
        "🔗 <b>Приватное лобби:</b> в Clash Royale создайте Дружеский бой "
        "(Клан/Друзья → выберите соперника → «Дружеский бой» → «Поделиться "
        "ссылкой») и пришлите мне ссылку командой:\n"
        f"<code>/lobby {match_id} ссылка</code>\n"
        "Я перешлю её сопернику. Если это уже сделал соперник — просто ждите "
        "ссылку от меня.\n\n"
        "Играйте и ждите, когда админ внесёт результат матча."
    )
    try:
        # бот не может написать первым, если игрок ни разу не писал ему в личку
        await bot.send_message(participant_row["user_id"], text, parse_mode="HTML")
    except Exception:
        logging.info(
            f"Не удалось отправить личное уведомление участнику user_id={participant_row['user_id']}"
        )


@dp.message(Command("lobby"))
async def cmd_lobby(message: Message, command: CommandObject):
    args = (command.args or "").split(maxsplit=1)
    if len(args) != 2:
        await message.answer(
            "Использование: /lobby <id_матча> <ссылка>\n\n"
            "Ссылку на приватный Дружеский бой можно получить в Clash Royale: "
            "Клан или Друзья → выберите соперника → «Дружеский бой» → "
            "«Поделиться ссылкой». Пришлите мне эту ссылку, и я перешлю её "
            "сопернику по матчу."
        )
        return

    try:
        match_id = int(args[0])
    except ValueError:
        await message.answer("id_матча должен быть числом.")
        return
    link = args[1].strip()

    match = await db.get_match(match_id)
    if not match:
        await message.answer("Матч с таким id не найден.")
        return
    if match["status"] != "pending":
        await message.answer("Этот матч уже завершён — лобби для него не нужно.")
        return

    p1 = await db.get_participant(match["player1_id"])
    p2 = await db.get_participant(match["player2_id"])
    sender_id = message.from_user.id

    me = None
    if p1 and sender_id == p1["user_id"]:
        me = p1
    elif p2 and sender_id == p2["user_id"]:
        me = p2
    elif not is_admin(sender_id):
        await message.answer("Эта команда — только для игроков этого матча (или админа турнира).")
        return

    await db.set_match_lobby_link(match_id, link, me["id"] if me else None)
    await message.answer("✅ Ссылка на лобби сохранена и переслана сопернику.")

    recipients = [p for p in (p1, p2) if p and (not me or p["id"] != me["id"])]
    for r in recipients:
        try:
            await bot.send_message(
                r["user_id"],
                f"🔗 Для вашего матча #{match_id} готово приватное лобби!\n"
                f"Перейдите по ссылке в Clash Royale, чтобы начать бой:\n{link}",
            )
        except Exception:
            logging.info(
                f"Не удалось переслать ссылку на лобби участнику user_id={r['user_id']}"
            )


async def announce_round(message, tournament_id: int, round_num: int):
    matches = await db.get_matches(tournament_id, round_num)
    lines = [f"🥊 <b>Раунд {round_num}</b>"]
    for m in matches:
        n1 = await nick(m["player1_id"])
        if m["status"] == "bye":
            lines.append(f"Матч #{m['id']}: {n1} — проходит дальше без игры (бай)")
        else:
            n2 = await nick(m["player2_id"])
            lines.append(f"Матч #{m['id']}: {n1} vs {n2}")
    await message.answer("\n".join(lines), parse_mode="HTML")

    for m in matches:
        if m["status"] != "pending":
            continue
        if config.READINESS_TIMEOUT_MINUTES > 0:
            await start_match_readiness_check(m, message)
        else:
            await activate_match(m, message)


async def activate_match(m, message):
    round_num = m["round"]
    n1 = await nick(m["player1_id"], escape=False)
    n2 = await nick(m["player2_id"], escape=False)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🏆 {n1}", callback_data=f"result:{m['id']}:1"),
        InlineKeyboardButton(text=f"🏆 {n2}", callback_data=f"result:{m['id']}:2"),
    ]])
    await message.answer(
        f"Матч #{m['id']}: {html.escape(n1)} vs {html.escape(n2)}\n"
        "Игрокам отправлена инструкция по созданию приватного лобби (ссылку "
        f"на Дружеский бой можно прислать мне командой /lobby {m['id']} &lt;ссылка&gt;).\n"
        "Админ, выберите победителя:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    p1 = await db.get_participant(m["player1_id"])
    p2 = await db.get_participant(m["player2_id"])
    await notify_player_of_match(p1, opponent_name=n2, match_id=m["id"], round_num=round_num)
    await notify_player_of_match(p2, opponent_name=n1, match_id=m["id"], round_num=round_num)


async def start_match_readiness_check(m, message):
    match_id = m["id"]
    check1, check2 = await db.create_readiness_checks(
        m["tournament_id"], match_id, [m["player1_id"], m["player2_id"]]
    )

    n1 = await nick(m["player1_id"], escape=False)
    n2 = await nick(m["player2_id"], escape=False)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"✅ Готов: {n1}", callback_data=f"ready:{check1}"),
        InlineKeyboardButton(text=f"✅ Готов: {n2}", callback_data=f"ready:{check2}"),
    ]])
    await message.answer(
        f"⏳ Матч #{match_id}: {html.escape(n1)} vs {html.escape(n2)}\n"
        f"Игроки, подтвердите готовность (у вас {config.READINESS_TIMEOUT_MINUTES} мин., "
        "иначе будет засчитано техническое поражение неготовому игроку).",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    p1 = await db.get_participant(m["player1_id"])
    p2 = await db.get_participant(m["player2_id"])
    for participant_row, opponent_name, check_id in (
        (p1, n2, check1),
        (p2, n1, check2),
    ):
        if not participant_row:
            continue
        personal_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Я готов", callback_data=f"ready:{check_id}")
        ]])
        try:
            await bot.send_message(
                participant_row["user_id"],
                f"⏳ Матч #{match_id} против {html.escape(opponent_name)}: подтвердите "
                f"готовность! У вас {config.READINESS_TIMEOUT_MINUTES} мин., иначе будет "
                "засчитано техническое поражение.",
                parse_mode="HTML",
                reply_markup=personal_keyboard,
            )
        except Exception:
            logging.info(
                f"Не удалось отправить личную проверку готовности участнику "
                f"user_id={participant_row['user_id']}"
            )

    task = asyncio.create_task(
        resolve_match_readiness(match_id, message.chat.id, config.READINESS_TIMEOUT_MINUTES * 60)
    )
    pending_match_tasks[match_id] = task


async def resolve_match_readiness(match_id: int, chat_id: int, timeout_seconds: float):
    try:
        await asyncio.sleep(timeout_seconds)
    except asyncio.CancelledError:
        return
    await resolve_match_readiness_now(match_id, chat_id)


async def resolve_match_readiness_now(match_id: int, chat_id: int):
    pending_match_tasks.pop(match_id, None)

    match = await db.get_match(match_id)
    if not match or match["status"] != "pending":
        return

    tournament = await db.get_tournament(match["tournament_id"])
    if not tournament or tournament["status"] == "finished":
        return

    chat = ChatTarget(chat_id)
    checks = await db.get_readiness_checks_for_match(match_id)
    confirmed_ids = {c["participant_id"] for c in checks if c["confirmed"]}

    p1_ready = match["player1_id"] in confirmed_ids
    p2_ready = match["player2_id"] in confirmed_ids

    if p1_ready and p2_ready:
        await activate_match(match, chat)
        return

    if p1_ready or p2_ready:
        winner_id = match["player1_id"] if p1_ready else match["player2_id"]
        loser_id = match["player2_id"] if p1_ready else match["player1_id"]
        winner_name = await nick(winner_id)
        loser_name = await nick(loser_id)
        await chat.answer(
            f"⌛ Матч #{match_id}: {loser_name} не подтвердил(а) готовность вовремя.\n"
            f"🏆 Техническая победа: <b>{winner_name}</b>",
            parse_mode="HTML",
        )
        await db.set_match_winner(match_id, winner_id)
        await advance_if_round_complete(chat, match["tournament_id"], match["round"])
    else:
        n1 = await nick(match["player1_id"])
        n2 = await nick(match["player2_id"])
        await chat.answer(
            f"⚠️ Матч #{match_id} ({n1} vs {n2}): ни один игрок не подтвердил "
            f"готовность вовремя. Админ, определите результат вручную: "
            f"/result {match_id} &lt;1|2&gt;",
            parse_mode="HTML",
        )


@dp.callback_query(F.data.startswith("ready:"))
async def cb_ready(callback: CallbackQuery):
    check_id = int(callback.data.split(":")[1])
    check = await db.get_readiness_check(check_id)
    if not check:
        await callback.answer("Проверка готовности не найдена.", show_alert=True)
        return

    participant = await db.get_participant(check["participant_id"])
    if not participant or participant["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для вас — подтверждать должен сам игрок.", show_alert=True)
        return

    match = await db.get_match(check["match_id"])
    if not match or match["status"] != "pending":
        await callback.answer("Матч уже завершён или отменён.", show_alert=True)
        return

    async with readiness_lock:
        already = bool(check["confirmed"])
        await db.confirm_readiness(check_id)
        checks = await db.get_readiness_checks_for_match(match["id"])
        all_confirmed = all(c["confirmed"] for c in checks)

    await callback.answer("Готовность уже была подтверждена ранее." if already else "✅ Готовность подтверждена!")

    if all_confirmed:
        task = pending_match_tasks.pop(match["id"], None)
        if task:
            task.cancel()
        tournament = await db.get_tournament(match["tournament_id"])
        chat = ChatTarget(tournament["chat_id"])
        await chat.answer(f"✅ Матч #{match['id']}: оба игрока подтвердили готовность!")
        await activate_match(match, chat)


@dp.message(Command("result"))
async def cmd_result(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только админам турнира.")
        return

    args = (command.args or "").split()
    if len(args) != 2 or args[1] not in ("1", "2"):
        await message.answer("Использование: /result <id_матча> <1|2>")
        return

    try:
        match_id = int(args[0])
    except ValueError:
        await message.answer("id_матча должен быть числом.")
        return

    await apply_match_result(message, match_id, args[1])


async def apply_match_result(reply_to: Message, match_id: int, choice: str) -> None:
    match = await db.get_match(match_id)
    if not match:
        await reply_to.answer("Матч с таким id не найден.")
        return
    if match["status"] != "pending":
        await reply_to.answer("Результат этого матча уже внесён (или это технический 'бай').")
        return

    winner_id = match["player1_id"] if choice == "1" else match["player2_id"]
    await db.set_match_winner(match_id, winner_id)

    winner_name = await nick(winner_id)
    await reply_to.answer(f"✅ Матч #{match_id}: победитель — {winner_name}", parse_mode="HTML")

    await advance_if_round_complete(reply_to, match["tournament_id"], match["round"])


@dp.callback_query(F.data.startswith("result:"))
async def cb_result(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Эта команда доступна только админам турнира.", show_alert=True)
        return

    _, match_id_str, choice = callback.data.split(":")
    match_id = int(match_id_str)

    match = await db.get_match(match_id)
    if not match or match["status"] != "pending":
        await callback.answer("Результат уже внесён или матч не найден.", show_alert=True)
        return

    await callback.answer()
    try:
        # убираем кнопки, чтобы результат не внесли дважды
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await apply_match_result(callback.message, match_id, choice)


async def advance_if_round_complete(message, tournament_id: int, round_num: int):
    matches = await db.get_matches(tournament_id, round_num)
    if any(m["status"] == "pending" for m in matches):
        return

    if len(matches) == 1:
        champion_id = matches[0]["winner_id"]
        champion_name = await nick(champion_id)
        await db.set_tournament_status(tournament_id, "finished")
        await message.answer(f"🏆🏆🏆 Турнир завершён! Чемпион: <b>{champion_name}</b> 🏆🏆🏆",
                              parse_mode="HTML")
        await announce_champion_to_channel(tournament_id, champion_name)
        return

    winners = [m["winner_id"] for m in sorted(matches, key=lambda x: x["position"])]
    pairs = bracket.pair_next_round(winners)

    next_matches = [
        {"position": i, "player1_id": p1, "player2_id": p2, "winner_id": None, "status": "pending"}
        for i, (p1, p2) in enumerate(pairs)
    ]
    next_round = round_num + 1
    await db.create_matches(tournament_id, next_round, next_matches)
    await announce_round(message, tournament_id, next_round)


async def announce_tournament_start_to_channel(tournament_name: str):
    if not config.CHANNEL_USERNAME:
        return
    text = (
        f"🎮 Открыта регистрация на турнир «{html.escape(tournament_name)}»!\n\n"
        "Жмите кнопку ниже, чтобы зарегистрироваться."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📝 Зарегистрироваться",
            url=f"https://t.me/{config.BOT_USERNAME}?start=register",
        )
    ]])
    try:
        await bot.send_message(config.CHANNEL_USERNAME, text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        logging.exception("Не удалось отправить объявление о начале турнира в канал")


async def announce_champion_to_channel(tournament_id: int, champion_name: str):
    if not config.CHANNEL_USERNAME:
        return
    tournament = await db.get_tournament(tournament_id)
    tournament_name = html.escape(tournament["name"]) if tournament else ""
    text = (
        f"🏆 Турнир «{tournament_name}» завершён!\n\n"
        f"Чемпион: <b>{champion_name}</b> 🎉\n\n"
        "Спасибо всем участникам! Следите за анонсами новых турниров."
    )
    try:
        await bot.send_message(config.CHANNEL_USERNAME, text, parse_mode="HTML")
    except Exception:
        logging.exception("Не удалось отправить объявление о чемпионе в канал")


@dp.message(Command("bracket"))
async def cmd_bracket(message: Message):
    tournament = await db.get_active_tournament(message.chat.id)
    if not tournament:
        await message.answer("Сейчас нет активного (или недавно завершённого) турнира.")
        return

    max_round = await db.get_max_round(tournament["id"])
    if max_round == 0:
        await message.answer("Сетка ещё не сформирована. Дождитесь /start_bracket от админа.")
        return

    lines = [f"📋 <b>Сетка турнира «{html.escape(tournament['name'])}»</b>"]
    for r in range(1, max_round + 1):
        matches = await db.get_matches(tournament["id"], r)
        lines.append(f"\n<u>Раунд {r}</u>")
        for m in matches:
            n1 = await nick(m["player1_id"])
            if m["status"] == "bye":
                lines.append(f"#{m['id']}: {n1} (бай)")
            else:
                n2 = await nick(m["player2_id"])
                if m["status"] == "done":
                    win = await nick(m["winner_id"])
                    lines.append(f"#{m['id']}: {n1} vs {n2} → 🏅 {win}")
                else:
                    lines.append(f"#{m['id']}: {n1} vs {n2} (не сыгран)")

    if tournament["status"] == "finished":
        lines.append("\n🏆 Турнир завершён.")

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("end_tournament"))
async def cmd_end_tournament(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только админам турнира.")
        return

    tournament = await db.get_active_tournament(message.chat.id)
    if not tournament:
        await message.answer("Сейчас нет активного турнира в этом чате.")
        return

    await db.set_tournament_status(tournament["id"], "finished")
    await message.answer(
        f"🛑 Турнир «{html.escape(tournament['name'])}» завершён досрочно администратором.\n"
        "Регистрация закрыта, сетка больше не обновляется."
    )
    await announce_tournament_cancelled_to_channel(tournament["name"])
    await refresh_admin_keyboard(message)


async def announce_tournament_cancelled_to_channel(tournament_name: str):
    if not config.CHANNEL_USERNAME:
        return
    text = f"🛑 Турнир «{html.escape(tournament_name)}» завершён досрочно организатором."
    try:
        await bot.send_message(config.CHANNEL_USERNAME, text, parse_mode="HTML")
    except Exception:
        logging.exception("Не удалось отправить объявление о досрочном завершении в канал")


@dp.message(Command("announce_channel"))
async def cmd_announce_channel(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только админам турнира.")
        return

    args = (command.args or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Использование: /announce_channel <@канал_или_id> <текст объявления>\n"
            "Пример: /announce_channel @your_channel 🏆 Турнир по Clash Royale! "
            "Регистрация открыта."
        )
        return

    channel, text = args[0], args[1]

    open_tournament = await db.get_latest_open_tournament()
    keyboard = None
    if open_tournament:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="📝 Зарегистрироваться",
                    url=f"https://t.me/{config.BOT_USERNAME}?start=register",
                )
            ]]
        )

    try:
        await bot.send_message(channel, text, reply_markup=keyboard)
        note = "" if open_tournament else "\n\nℹ️ Нет турнира с открытой регистрацией — кнопку не добавил."
        await message.answer("✅ Объявление опубликовано в канале." + note)
    except Exception as e:
        await message.answer(
            f"Не удалось опубликовать в канал: {e}\n\n"
            "Проверьте: 1) бот добавлен в канал как администратор с правом "
            "публикации сообщений; 2) @канал указан верно (или используйте "
            "числовой id канала, если у него нет username)."
        )


async def main():
    await db.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
