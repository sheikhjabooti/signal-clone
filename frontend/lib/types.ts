export type User = {
  id: number;
  username: string;
  display_name: string;
  avatar_url: string | null;
  color: string;
  last_seen: string;
  online?: boolean;
};
export type Session = { user: User; csrf_token: string };
export type Member = User & { role: "admin" | "member" };
export type Message = {
  id: number;
  conversation_id: number;
  client_message_id: string;
  sender_id: number;
  sender: User;
  body: string;
  created_at: string;
  status: "sent" | "delivered" | "read";
  delivered_at: string | null;
  read_at: string | null;
  recipient_count: number;
  delivered_count: number;
  read_count: number;
  reply_to_id: number | null;
  reply: { id: number; body: string; sender_name: string } | null;
  reactions: { emoji: string; count: number; mine: boolean }[];
};
export type Conversation = {
  id: number;
  kind: "direct" | "group";
  name: string;
  members: Member[];
  peer: User | null;
  role: "admin" | "member";
  unread_count: number;
  created_at: string;
  updated_at: string;
  last_message: Message | null;
};
export type History = {
  messages: Message[];
  has_more: boolean;
  through_id: number;
  next_after_id: number;
  next_before_id: number | null;
};
export type MessageCache = {
  items: Message[];
  through: number;
  older: number | null;
  hasOlder: boolean;
};
export type PendingMessage = {
  client_message_id: string;
  conversation_id: number;
  body: string;
  created_at: string;
  reply: Message | null;
  state: "sending" | "failed";
  error?: string;
};
export type LiveEvent = {
  type: string;
  conversation_id?: number;
  message_id?: number;
  sender_id?: number;
  user_id?: number;
  removed?: boolean;
  online?: boolean;
  active?: boolean;
  ttl_ms?: number;
};
