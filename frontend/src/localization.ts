import { de, type FrontendMessageKey } from "./catalog.de";

export function translate(
  texts: Record<string, string>,
  key: string,
  values: Record<string, string | number> = {},
): string {
  const source = texts[key] ?? de[key as FrontendMessageKey] ?? key;
  return source.replace(/\{(\w+)\}/g, (_match, variable: string) =>
    String(values[variable] ?? `{${variable}}`),
  );
}
