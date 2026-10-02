// V2 的线性图标（24×24，1.5px 描边），从 prototype.js 原样迁移
export const iconPaths = {
  chat: 'M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5A8.5 8.5 0 0 1 10.5 3h2a8.5 8.5 0 0 1 8.5 8.5ZM7 10h10M7 14h6',
  ticket: 'M4 4h16v5a3 3 0 0 0 0 6v5H4v-5a3 3 0 0 0 0-6V4Zm10 0v3m0 3v4m0 3v3',
  users:
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M15 3a4 4 0 0 1 0 8m7 10v-2a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  box: 'm12 3 9 5v10l-9 5-9-5V8l9-5Zm0 10 9-5M12 13 3 8m9 5v10M7.5 5.5l9 5',
  book: 'M12 5c-3-2-7-2-10-1v16c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1Zm0 0v16',
  chart: 'M3 3v18h18M7 16v-5m5 5V7m5 9v-8',
  settings:
    'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM4 4l3 1 2-3h6l2 3 3-1 2 5-2 3 2 3-2 5-3-1-2 3H9l-2-3-3 1-2-5 2-3-2-3 2-5Z',
  search: 'm21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
  chevron: 'm8 5 7 7-7 7',
  down: 'm6 9 6 6 6-6',
  plus: 'M12 5v14M5 12h14',
  arrow: 'M5 12h14m-6-6 6 6-6 6',
  close: 'm6 6 12 12M6 18 18 6',
  check: 'm5 12 4 4L19 6',
  clock: 'M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
  spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z',
  send: 'm22 2-7 20-4-9-9-4 20-7ZM22 2 11 13',
  file: 'M14 2H4v20h16V8l-6-6Zm0 0v6h6M8 13h8m-8 4h5',
  headset: 'M3 14v-2a9 9 0 0 1 18 0v2M3 12h3v8H3v-8Zm15 0h3v8h-3v-8Zm3 8v2h-8',
  shield: 'm12 2 9 4v6c0 6-9 10-9 10S3 18 3 12V6l9-4Zm-4 10 3 3 5-6',
  truck: 'M1 4h13v13H1V4Zm13 5h4l4 4v4h-8M8 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm12 0a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
  back: 'M20 12H4m6-6-6 6 6 6',
  info: 'M12 11v6m0-10v.1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
} as const

export type IconName = keyof typeof iconPaths
