/** Цвет инженера — из макета (DispatcherFlow, COL): основной для точки и обводки, заливка для заявки. */
export const ENGINEER_COLORS = [
  ['#E4572E', '#FCE3DB'], ['#F29E1F', '#FDEFD6'], ['#2FA84F', '#DDF3E2'], ['#1F8FD1', '#D9EEFA'],
  ['#C2185B', '#F9DCE8'], ['#00A3A3', '#D5F2F2'], ['#A0782C', '#F3E9D6'], ['#5B7C99', '#E3EAF0'],
  ['#3F51B5', '#E0E4F7'], ['#7CB342', '#EAF4DE'], ['#6D4C41', '#EDE3DF'], ['#9E9D24', '#F1F1D5']];
export const IDLE = '#C9CED6';

export function colorsFor(ids) {
  return Object.fromEntries(ids.map((id, i) => {
    const [main, tint] = ENGINEER_COLORS[i % ENGINEER_COLORS.length];
    return [id, { main, tint }];
  }));
}
