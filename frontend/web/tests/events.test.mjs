import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseFrames } from '../src/api/sseFrames.ts'

test('parseFrames 拆分事件并保留不完整的尾部', () => {
  const seen = []
  const rest = parseFrames(': connected\n\ndata: {"type":"a"}\n\ndata: {"type":"b"}\r\n\r\ndata: {"ty', (e) => seen.push(e))
  assert.deepEqual(seen, [{ type: 'a' }, { type: 'b' }])
  assert.equal(rest, 'data: {"ty')
})

test('parseFrames 忽略心跳和坏数据', () => {
  const seen = []
  parseFrames(': ping\n\ndata: not-json\n\ndata: {"ok":1}\n\n', (e) => seen.push(e))
  assert.deepEqual(seen, [{ ok: 1 }])
})
