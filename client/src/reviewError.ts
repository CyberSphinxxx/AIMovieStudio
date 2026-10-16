type Named = { id: string; name: string };

export function reviewError(
  message: string,
  plan: {
    characters: Named[];
    locations: Named[];
    props?: Named[];
  } | null,
) {
  let readable = message
    .replace(
      /^CANON_CONFLICT:\s*/,
      "This cut conflicts with saved story details. ",
    )
    .replace(/ Canon evidence: [^.]+\.$/, "");
  for (const item of [
    ...(plan?.characters ?? []),
    ...(plan?.locations ?? []),
    ...(plan?.props ?? []),
  ]) {
    readable = readable.split(item.id).join(item.name);
  }
  return readable.replace(
    /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,
    "a saved story item",
  );
}
