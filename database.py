import aiosqlite
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    game TEXT NOT NULL DEFAULT 'Clash Royale',
    status TEXT NOT NULL DEFAULT 'registration',  -- registration | in_progress | finished
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    nickname TEXT NOT NULL,
    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, user_id),
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    round INTEGER NOT NULL,
    position INTEGER NOT NULL,
    player1_id INTEGER,          -- ссылается на participants.id
    player2_id INTEGER,          -- NULL = "бай" (авто-проход)
    winner_id INTEGER,           -- ссылается на participants.id
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | bye
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
);

CREATE TABLE IF NOT EXISTS match_lobbies (
    match_id INTEGER PRIMARY KEY,
    link TEXT NOT NULL,
    submitted_by INTEGER,          -- participants.id того, кто прислал ссылку; NULL, если добавил админ
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(id)
);

CREATE TABLE IF NOT EXISTS readiness_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    match_id INTEGER,              -- NULL = проверка перед стартом турнира
    participant_id INTEGER NOT NULL,
    confirmed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id),
    FOREIGN KEY (match_id) REFERENCES matches(id)
);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def create_tournament(chat_id: int, name: str, game: str = "Clash Royale") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tournaments (chat_id, name, game, status) VALUES (?, ?, ?, 'registration')",
            (chat_id, name, game),
        )
        await db.commit()
        return cur.lastrowid


async def get_active_tournament(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM tournaments WHERE chat_id = ? AND status != 'finished' "
            "ORDER BY id DESC LIMIT 1",
            (chat_id,),
        )
        return await cur.fetchone()


async def get_latest_open_tournament():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM tournaments WHERE status = 'registration' ORDER BY id DESC LIMIT 1"
        )
        return await cur.fetchone()


async def get_tournament(tournament_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM tournaments WHERE id = ?", (tournament_id,))
        return await cur.fetchone()


async def set_tournament_status(tournament_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tournaments SET status = ? WHERE id = ?", (status, tournament_id))
        await db.commit()


async def add_participant(tournament_id: int, user_id: int, username: str, nickname: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO participants (tournament_id, user_id, username, nickname) "
                "VALUES (?, ?, ?, ?)",
                (tournament_id, user_id, username, nickname),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_participants(tournament_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM participants WHERE tournament_id = ? ORDER BY id", (tournament_id,)
        )
        return await cur.fetchall()


async def get_participant(participant_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM participants WHERE id = ?", (participant_id,))
        return await cur.fetchone()


async def get_participant_by_user(tournament_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM participants WHERE tournament_id = ? AND user_id = ?",
            (tournament_id, user_id),
        )
        return await cur.fetchone()


async def remove_participant(tournament_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM participants WHERE tournament_id = ? AND user_id = ?",
            (tournament_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_user_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute(
            "SELECT id, tournament_id FROM participants WHERE user_id = ?", (user_id,)
        )
        rows = await cur.fetchall()

        empty = {
            "tournaments_played": 0,
            "matches_played": 0,
            "wins": 0,
            "losses": 0,
            "championships": 0,
        }
        if not rows:
            return empty

        participant_ids = [r["id"] for r in rows]
        tournament_ids = sorted({r["tournament_id"] for r in rows})
        placeholders = ",".join("?" * len(participant_ids))

        cur = await db.execute(
            f"SELECT COUNT(*) FROM matches WHERE status = 'done' "
            f"AND (player1_id IN ({placeholders}) OR player2_id IN ({placeholders}))",
            participant_ids + participant_ids,
        )
        matches_played = (await cur.fetchone())[0]

        cur = await db.execute(
            f"SELECT COUNT(*) FROM matches WHERE status = 'done' "
            f"AND winner_id IN ({placeholders})",
            participant_ids,
        )
        wins = (await cur.fetchone())[0]

        championships = 0
        for tid in tournament_ids:
            cur = await db.execute("SELECT status FROM tournaments WHERE id = ?", (tid,))
            trow = await cur.fetchone()
            if not trow or trow["status"] != "finished":
                continue

            cur = await db.execute(
                "SELECT COALESCE(MAX(round), 0) FROM matches WHERE tournament_id = ?", (tid,)
            )
            max_round = (await cur.fetchone())[0]
            if max_round == 0:
                continue

            cur = await db.execute(
                "SELECT winner_id FROM matches WHERE tournament_id = ? AND round = ?",
                (tid, max_round),
            )
            final_matches = await cur.fetchall()
            if (
                len(final_matches) == 1
                and final_matches[0]["winner_id"] in participant_ids
            ):
                championships += 1

        return {
            "tournaments_played": len(tournament_ids),
            "matches_played": matches_played,
            "wins": wins,
            "losses": matches_played - wins,
            "championships": championships,
        }


async def create_matches(tournament_id: int, round_num: int, matches: list[dict]):
    async with aiosqlite.connect(DB_PATH) as db:
        for m in matches:
            await db.execute(
                "INSERT INTO matches (tournament_id, round, position, player1_id, "
                "player2_id, winner_id, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    tournament_id,
                    round_num,
                    m["position"],
                    m["player1_id"],
                    m.get("player2_id"),
                    m.get("winner_id"),
                    m.get("status", "pending"),
                ),
            )
        await db.commit()


async def get_matches(tournament_id: int, round_num: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if round_num is None:
            cur = await db.execute(
                "SELECT * FROM matches WHERE tournament_id = ? ORDER BY round, position",
                (tournament_id,),
            )
        else:
            cur = await db.execute(
                "SELECT * FROM matches WHERE tournament_id = ? AND round = ? ORDER BY position",
                (tournament_id, round_num),
            )
        return await cur.fetchall()


async def get_match(match_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
        return await cur.fetchone()


async def set_match_winner(match_id: int, winner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE matches SET winner_id = ?, status = 'done' WHERE id = ?",
            (winner_id, match_id),
        )
        await db.commit()


async def get_max_round(tournament_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COALESCE(MAX(round), 0) FROM matches WHERE tournament_id = ?",
            (tournament_id,),
        )
        row = await cur.fetchone()
        return row[0]


async def create_readiness_checks(
    tournament_id: int, match_id: int | None, participant_ids: list[int]
) -> list[int]:
    ids = []
    async with aiosqlite.connect(DB_PATH) as db:
        for pid in participant_ids:
            cur = await db.execute(
                "INSERT INTO readiness_checks (tournament_id, match_id, participant_id, confirmed) "
                "VALUES (?, ?, ?, 0)",
                (tournament_id, match_id, pid),
            )
            ids.append(cur.lastrowid)
        await db.commit()
    return ids


async def get_readiness_check(check_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM readiness_checks WHERE id = ?", (check_id,))
        return await cur.fetchone()


async def confirm_readiness(check_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE readiness_checks SET confirmed = 1 WHERE id = ?", (check_id,)
        )
        await db.commit()
        return cur.rowcount > 0


async def get_readiness_checks_for_match(match_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM readiness_checks WHERE match_id = ? ORDER BY id", (match_id,)
        )
        return await cur.fetchall()


async def set_match_lobby_link(match_id: int, link: str, submitted_by: int | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO match_lobbies (match_id, link, submitted_by) VALUES (?, ?, ?) "
            "ON CONFLICT(match_id) DO UPDATE SET link = excluded.link, "
            "submitted_by = excluded.submitted_by, created_at = CURRENT_TIMESTAMP",
            (match_id, link, submitted_by),
        )
        await db.commit()


async def get_match_lobby_link(match_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM match_lobbies WHERE match_id = ?", (match_id,))
        return await cur.fetchone()


async def get_pre_bracket_checks(tournament_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM readiness_checks WHERE tournament_id = ? AND match_id IS NULL "
            "ORDER BY id",
            (tournament_id,),
        )
        return await cur.fetchall()
