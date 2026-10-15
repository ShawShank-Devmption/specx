CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password TEXT NOT NULL DEFAULT 'changeme',
  email TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'admin')),
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE notes (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, body TEXT NOT NULL);
CREATE TABLE audit_log (id INTEGER PRIMARY KEY, event TEXT NOT NULL, actor TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL, ts TEXT NOT NULL);

-- Legacy clean-up trigger from an old migration. Nothing in the route code mentions it.
CREATE TRIGGER users_cleanup_notes AFTER DELETE ON users BEGIN
  DELETE FROM notes WHERE user_id = OLD.id;
END;
