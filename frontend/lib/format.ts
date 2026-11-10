export function initials(name: string) {
  return name.trim().split(/\s+/).slice(0, 2).map(n => n[0]).join("").toUpperCase();
}
export function time(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}
export function listTime(value: string) {
  const date = new Date(value), today = new Date();
  if (date.toDateString() === today.toDateString()) return time(value);
  const yesterday = new Date(); yesterday.setDate(yesterday.getDate() - 1);
  return date.toDateString() === yesterday.toDateString() ? "Yesterday" : date.toLocaleDateString([], { month: "short", day: "numeric" });
}
export function dayLabel(value: string) {
  const date = new Date(value), today = new Date();
  if (date.toDateString() === today.toDateString()) return "Today";
  const yesterday = new Date(); yesterday.setDate(yesterday.getDate() - 1);
  return date.toDateString() === yesterday.toDateString() ? "Yesterday" : date.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" });
}
export function lastSeen(value: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 1) return "Last seen just now";
  if (minutes < 60) return `Last seen ${minutes}m ago`;
  return `Last seen ${listTime(value)}`;
}
