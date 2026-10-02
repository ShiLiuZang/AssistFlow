import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readChatStream } from '../src/api/chatStream.ts'

function response(text, size = 1) {
  const bytes = new TextEncoder().encode(text)
  return new Response(new ReadableStream({ start(controller) {
    for (let i = 0; i < bytes.length; i += size) controller.enqueue(bytes.slice(i, i + size))
    controller.close()
  } }), { headers: { 'content-type': 'text/event-stream' } })
}

test('UTF-8 split bytes, CRLF and interrupt survive network chunking', async () => {
  const events = []
  await readChatStream(response(': heartbeat\r\n\r\ndata: {"delta":"你好"}\r\n\r\ndata: {"event":"interrupt","kind":"select_order"}\n\ndata: [DONE]\n\n'), e => events.push(e))
  assert.deepEqual(events, [{ delta: '你好' }, { event: 'interrupt', kind: 'select_order' }])
})

test('server error and missing completion cannot be mistaken for success', async () => {
  await assert.rejects(readChatStream(response('event: error\ndata: {"message":"上游失败"}\n\ndata: [DONE]\n\n'), () => {}), /上游失败/)
  await assert.rejects(readChatStream(response('data: {"delta":"半条回复"}\n\n'), () => {}), /连接提前结束/)
  await assert.rejects(readChatStream(new Response('{"detail":"会话不存在"}', { status: 404 }), () => {}), /会话不存在/)
})
