"""Параллельные запросы к одной сессии не мешают друг другу."""
from concurrent.futures import ThreadPoolExecutor


def test_parallel_reads_of_one_session_all_succeed(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 2})
    client.post(f"/api/sessions/{sid}/plan")
    paths = [f"/api/sessions/{sid}", f"/api/sessions/{sid}/plan", f"/api/sessions/{sid}/engineers",
             f"/api/sessions/{sid}/requests", f"/api/sessions/{sid}/settings", f"/api/sessions/{sid}/catalog"] * 8
    with ThreadPoolExecutor(max_workers=12) as ex:
        codes = list(ex.map(lambda p: client.get(p).status_code, paths))
    assert codes == [200] * len(paths)


def test_each_thread_gets_its_own_connection(client):
    from app import state
    import threading
    seen = []
    t = threading.Thread(target=lambda: seen.append(state.con()))
    t.start(); t.join()
    assert seen[0] is not state.con()
    assert seen[0].execute("PRAGMA database_list").fetchone()[2] == state.con().execute("PRAGMA database_list").fetchone()[2]


def test_short_lived_threads_do_not_leak_connections(client, monkeypatch):
    """anyio отзывает простаивающие потоки пула — соединение должно уходить с потоком
    (threading.local), а не копиться в модульном реестре state (иначе на реальном
    сервере — утечка открытых соединений при каждом отозванном потоке)."""
    from app import state
    import threading
    import weakref
    import gc
    import sqlite3

    # нет глобального словаря/списка соединений на все потоки — только threading.local
    assert isinstance(state._local, threading.local)
    assert not any(isinstance(v, dict) for k, v in vars(state).items() if not k.startswith("__"))

    # sqlite3.Connection сама по себе не поддерживает weakref — подставляем подкласс,
    # чтобы проверить, что соединение действительно освобождается вместе с потоком.
    class _WeakableConnection(sqlite3.Connection):
        pass

    real_sqlite_connect = sqlite3.connect

    def connect_weakable(*args, **kwargs):
        kwargs.setdefault("factory", _WeakableConnection)
        return real_sqlite_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect_weakable)

    refs = []
    for _ in range(20):
        box = {}
        t = threading.Thread(target=lambda: box.setdefault("con", state.con()))
        t.start()
        t.join()
        refs.append(weakref.ref(box["con"]))
        del box, t

    gc.collect()
    alive = sum(1 for r in refs if r() is not None)
    assert alive == 0
