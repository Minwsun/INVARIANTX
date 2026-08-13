export function normalizeApiBase(value) {
  if (!value) return "http://localhost:8000";
  if (/^https?:\/\//.test(value)) return value;
  return `https://${value.includes(".") ? value : `${value}.onrender.com`}`;
}
