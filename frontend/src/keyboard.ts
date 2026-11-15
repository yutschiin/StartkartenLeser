export function installSpaceButtonActivation(
  root: Document = document,
): () => void {
  let pressedButton: HTMLButtonElement | null = null;
  const isButton = (target: EventTarget | null): target is HTMLButtonElement =>
    target instanceof HTMLButtonElement && !target.disabled;

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== " " || event.isComposing) return;
    const target = event.target;
    if (!isButton(target)) return;
    event.preventDefault();
    if (event.repeat || pressedButton) return;
    pressedButton = target;
  };
  const onKeyUp = (event: KeyboardEvent) => {
    if (event.key !== " ") return;
    const button = pressedButton;
    pressedButton = null;
    if (button && button.isConnected && root.activeElement === button && !button.disabled) {
      button.click();
    }
  };
  const onBlur = () => {
    pressedButton = null;
  };

  root.addEventListener("keydown", onKeyDown, true);
  root.addEventListener("keyup", onKeyUp, true);
  window.addEventListener("blur", onBlur);
  return () => {
    root.removeEventListener("keydown", onKeyDown, true);
    root.removeEventListener("keyup", onKeyUp, true);
    window.removeEventListener("blur", onBlur);
    pressedButton = null;
  };
}

export function focusNextReviewControl(
  current: HTMLElement,
  root: ParentNode,
  backwards = false,
): boolean {
  const controls = Array.from(
    root.querySelectorAll<HTMLElement>("[data-review-control]"),
  ).filter((element) => !element.hasAttribute("disabled"));
  const index = controls.indexOf(current);
  const next = index >= 0 ? controls[index + (backwards ? -1 : 1)] : undefined;
  next?.focus();
  return Boolean(next);
}
