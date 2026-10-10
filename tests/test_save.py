"""builder.save.save: a stale workflow id is created again; a new workflow is saved twice."""
import json

import pytest

from builder import save as save_mod


class FakeFreya:
    """The kit's save_workflow over an in-memory platform: update of an unknown id raises like freya.api."""

    def __init__(self, known):
        self.known, self.calls = set(known), []

    def save_workflow(self, slot, wf, state_file):
        import pathlib
        f = pathlib.Path(state_file)
        state = json.loads(f.read_text()) if f.exists() else {}
        if slot in state:
            wid = state[slot]["workflow_id"]
            self.calls.append(("update", wid))
            if wid not in self.known:
                raise RuntimeError("PUT /api/v2/workflow/" + wid + ' -> 404: {"success":false}')
            state[slot]["version"] = 2
        else:
            wid = "new-" + str(len(self.known))
            self.known.add(wid)
            self.calls.append(("create", wid))
            state[slot] = {"workflow_id": wid, "agent_id": "a-" + wid}
        f.write_text(json.dumps(state))
        return state[slot]


@pytest.fixture
def fake(tmp_path, monkeypatch):
    def make(state, known):
        path = tmp_path / ".freya-agents.json"
        if state is not None:
            path.write_text(json.dumps(state))
        client = FakeFreya(known)
        monkeypatch.setattr(save_mod, "STATE_FILE", path)
        monkeypatch.setattr(save_mod, "freya", client)
        return client, path
    return make


def test_stale_id_is_created_again_and_saved_twice(fake):
    client, path = fake({"brief-a": {"workflow_id": "gone", "agent_id": "x"}, "other": {"workflow_id": "k"}}, {"k"})
    saved = save_mod.save("brief-a", {})
    assert [c[0] for c in client.calls] == ["update", "create", "update"]
    assert saved["workflow_id"] == "new-1" and saved["version"] == 2
    assert json.loads(path.read_text())["other"] == {"workflow_id": "k"}


def test_first_save_is_saved_twice(fake):
    client, _ = fake(None, set())
    assert save_mod.save("brief-a", {})["version"] == 2
    assert [c[0] for c in client.calls] == ["create", "update"]


def test_existing_id_is_updated_once(fake):
    client, _ = fake({"brief-a": {"workflow_id": "k", "agent_id": "x"}}, {"k"})
    save_mod.save("brief-a", {})
    assert client.calls == [("update", "k")]


def test_other_errors_are_raised(fake):
    client, _ = fake(None, set())
    client.save_workflow = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("POST /api/v2/workflow -> 500: x"))
    with pytest.raises(RuntimeError):
        save_mod.save("brief-a", {})
