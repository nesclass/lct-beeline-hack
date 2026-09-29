"""Соединение с базой на поток и общий замок вокруг расчёта.

sqlite не терпит параллельной работы одного соединения из нескольких потоков:
синхронные эндпоинты FastAPI исполняются в пуле потоков, и общий курсор путает
результаты параллельных запросов (случайные 500 и ложные 404). Поэтому у
каждого потока — своё соединение в threading.local, открытое к одному и тому
же файлу базы. Пул потоков anyio отзывает простаивающие потоки — с
threading.local соединение уходит вместе с потоком, никакого глобального
реестра соединений нет.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from . import store

_local = threading.local()
_meta_lock = threading.Lock()
_path: Path | None = None
_gen = 0
lock = threading.Lock()


def con() -> sqlite3.Connection:
    """Соединение текущего потока. Открывается store.connect(path) при первом
    обращении из потока (или когда use() сменила базу после последнего
    обращения из этого потока); путь — тот, что задан через use(), иначе
    store.DB_PATH."""
    with _meta_lock:
        path, gen = _path, _gen

    if getattr(_local, "con", None) is not None and getattr(_local, "gen", None) == gen:
        return _local.con

    old = getattr(_local, "con", None)
    if old is not None:
        try:
            old.close()
        except sqlite3.Error:
            pass

    _local.con = store.connect(path or store.DB_PATH)
    _local.gen = gen
    return _local.con


def use(connection: sqlite3.Connection) -> None:
    """Подменить соединение — для тестов.

    Запоминает путь к файлу базы переданного соединения и увеличивает
    поколение, чтобы каждый поток при следующем обращении к con() закрыл
    старое соединение и открыл новое — к тому же файлу. Само переданное
    соединение становится соединением вызывающего потока немедленно.
    """
    global _path, _gen
    db_path = connection.execute("PRAGMA database_list").fetchone()[2]
    with _meta_lock:
        _path = Path(db_path) if db_path else None
        _gen += 1
        gen = _gen

    old = getattr(_local, "con", None)
    if old is not None and old is not connection:
        try:
            old.close()
        except sqlite3.Error:
            pass

    _local.con = connection
    _local.gen = gen
