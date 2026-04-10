/**
 * DOM-walk text highlighter for in-chat search. Wraps each occurrence
 * of `query` (case-insensitive) in a `<mark class="chat-search-highlight">`
 * inside `root`. The mark is inline-only so layout is unaffected and
 * `clearHighlights` reverses the operation cleanly.
 */

const HIGHLIGHT_CLASS = "chat-search-highlight";
const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "TEXTAREA", "INPUT", "MARK"]);

export function highlightText(root: HTMLElement, query: string): void {
  if (!query) return;
  const lowerQ = query.toLowerCase();

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || SKIP_TAGS.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
      return node.nodeValue?.toLowerCase().includes(lowerQ)
        ? NodeFilter.FILTER_ACCEPT
        : NodeFilter.FILTER_REJECT;
    },
  });

  // Collect first to avoid mutating during walk.
  const targets: Text[] = [];
  let node = walker.nextNode();
  while (node) {
    targets.push(node as Text);
    node = walker.nextNode();
  }

  for (const textNode of targets) {
    const text = textNode.nodeValue ?? "";
    const lowerText = text.toLowerCase();
    const fragment = document.createDocumentFragment();
    let lastIdx = 0;
    let idx = lowerText.indexOf(lowerQ);
    while (idx !== -1) {
      if (idx > lastIdx) {
        fragment.appendChild(document.createTextNode(text.slice(lastIdx, idx)));
      }
      const mark = document.createElement("mark");
      mark.className = HIGHLIGHT_CLASS;
      mark.textContent = text.slice(idx, idx + lowerQ.length);
      fragment.appendChild(mark);
      lastIdx = idx + lowerQ.length;
      idx = lowerText.indexOf(lowerQ, lastIdx);
    }
    if (lastIdx < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(lastIdx)));
    }
    textNode.parentNode?.replaceChild(fragment, textNode);
  }
}

export function clearHighlights(root: HTMLElement): void {
  const marks = root.querySelectorAll(`mark.${HIGHLIGHT_CLASS}`);
  for (const mark of Array.from(marks)) {
    mark.parentNode?.replaceChild(document.createTextNode(mark.textContent ?? ""), mark);
  }
  // Merge split text nodes so the next pass sees clean strings.
  root.normalize();
}
