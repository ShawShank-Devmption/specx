INSERT INTO users (id, username, password, email, role, active) VALUES
  (1, 'root', 'root123', 'root@example.com', 'admin', 1),
  (2, 'bob', 'bob123', 'bob@example.com', 'editor', 1),
  (3, 'carol', 'carol123', 'carol@example.com', 'viewer', 1),
  (4, 'erin', 'erin123', 'erin@example.com', 'viewer', 1),
  (5, 'hank', 'hank123', 'hank@example.com', 'editor', 1),
  (6, 'ivy', 'ivy123', 'ivy@example.com', 'viewer', 1);
INSERT INTO notes (id, user_id, body) VALUES
  (1, 2, 'Quarterly review draft'),
  (2, 2, 'Vendor contacts'),
  (3, 3, 'Onboarding checklist'),
  (4, 3, 'Holiday rota'),
  (5, 4, 'Design notes'),
  (6, 5, 'Incident log'),
  (7, 5, 'On-call handover'),
  (8, 6, 'Expense receipts'),
  (9, 6, 'Training plan'),
  (10, 1, 'Admin runbook');
