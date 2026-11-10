"""Initial schema: accounts, memberships, messages, receipts and reactions."""
from alembic import op
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = ['\nCREATE TABLE users (\n\tid INTEGER NOT NULL, \n\tusername VARCHAR(32) NOT NULL, \n\tdisplay_name VARCHAR(64) NOT NULL, \n\tavatar VARCHAR(80), \n\tcolor VARCHAR(16) NOT NULL, \n\tcreated_at VARCHAR(32) NOT NULL, \n\tlast_seen VARCHAR(32) NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (username)\n)\n\n', '\nCREATE TABLE contacts (\n\towner_id INTEGER NOT NULL, \n\tcontact_id INTEGER NOT NULL, \n\tPRIMARY KEY (owner_id, contact_id), \n\tCONSTRAINT contact_not_self CHECK (owner_id != contact_id), \n\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE, \n\tFOREIGN KEY(contact_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n', "\nCREATE TABLE conversations (\n\tid INTEGER NOT NULL, \n\tkind VARCHAR(8) NOT NULL, \n\tname VARCHAR(80), \n\tcreator_id INTEGER NOT NULL, \n\tdirect_key VARCHAR(50), \n\tcreated_at VARCHAR(32) NOT NULL, \n\tupdated_at VARCHAR(32) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT conversation_kind CHECK (kind IN ('direct','group')), \n\tCONSTRAINT direct_key_required CHECK ((kind = 'direct' AND direct_key IS NOT NULL) OR (kind = 'group' AND direct_key IS NULL)), \n\tFOREIGN KEY(creator_id) REFERENCES users (id), \n\tUNIQUE (direct_key)\n)\n\n", '\nCREATE TABLE sessions (\n\ttoken_hash VARCHAR(64) NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\tcsrf_token VARCHAR(64) NOT NULL, \n\texpires_at VARCHAR(32) NOT NULL, \n\tPRIMARY KEY (token_hash), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n', 'CREATE INDEX ix_sessions_expires_at ON sessions (expires_at)', 'CREATE INDEX ix_sessions_user_id ON sessions (user_id)', "\nCREATE TABLE conversation_members (\n\tconversation_id INTEGER NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\trole VARCHAR(8) NOT NULL, \n\tactive BOOLEAN NOT NULL, \n\tjoined_at VARCHAR(32) NOT NULL, \n\tleft_at VARCHAR(32), \n\tPRIMARY KEY (conversation_id, user_id), \n\tCONSTRAINT member_role CHECK (role IN ('admin','member')), \n\tFOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n", 'CREATE INDEX ix_members_user_active ON conversation_members (user_id, active)', '\nCREATE TABLE messages (\n\tid INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, \n\tconversation_id INTEGER NOT NULL, \n\tsender_id INTEGER NOT NULL, \n\tclient_message_id VARCHAR(64) NOT NULL, \n\tbody TEXT NOT NULL, \n\tcreated_at VARCHAR(32) NOT NULL, \n\treply_to_id INTEGER, \n\tCONSTRAINT uq_message_retry UNIQUE (sender_id, client_message_id), \n\tCONSTRAINT message_length CHECK (length(body) BETWEEN 1 AND 4000), \n\tFOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(sender_id) REFERENCES users (id), \n\tFOREIGN KEY(reply_to_id) REFERENCES messages (id) ON DELETE SET NULL\n)\n\n', 'CREATE INDEX ix_message_history ON messages (conversation_id, id)', '\nCREATE TABLE message_recipients (\n\tmessage_id INTEGER NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\tdelivered_at VARCHAR(32), \n\tread_at VARCHAR(32), \n\tPRIMARY KEY (message_id, user_id), \n\tCONSTRAINT read_implies_delivered CHECK (read_at IS NULL OR delivered_at IS NOT NULL), \n\tFOREIGN KEY(message_id) REFERENCES messages (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n', 'CREATE INDEX ix_recipients_unread ON message_recipients (user_id, read_at, message_id)', 'CREATE INDEX ix_recipients_delivery ON message_recipients (user_id, delivered_at, message_id)', '\nCREATE TABLE reactions (\n\tmessage_id INTEGER NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\temoji VARCHAR(16) NOT NULL, \n\tPRIMARY KEY (message_id, user_id), \n\tFOREIGN KEY(message_id) REFERENCES messages (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n']

def upgrade():
    for statement in STATEMENTS:
        op.execute(statement)

def downgrade():
    op.drop_table('reactions')
    op.drop_table('message_recipients')
    op.drop_table('messages')
    op.drop_table('conversation_members')
    op.drop_table('sessions')
    op.drop_table('conversations')
    op.drop_table('contacts')
    op.drop_table('users')
