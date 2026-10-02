import { test } from 'node:test'
import assert from 'node:assert/strict'
import { authHeaders, hasRole, missingPermission, setCustomer, setStaff } from '../src/auth/session.ts'

test('按路径选择令牌：顾客接口用顾客令牌，后台接口用员工令牌，公开接口不带', () => {
  setStaff({ token: 'staff-token', username: 'alice', role: 'reviewer' })
  setCustomer({ token: 'customer-token', userId: 'u1' })
  assert.deepEqual(authHeaders('/api/graph-chat'), { Authorization: 'Bearer customer-token' })
  assert.deepEqual(authHeaders('/api/conversations/3/messages'), { Authorization: 'Bearer customer-token' })
  assert.deepEqual(authHeaders('/api/kb/chunks'), { Authorization: 'Bearer staff-token' })
  assert.deepEqual(authHeaders('/api/auth/login'), {})
  assert.deepEqual(authHeaders('/api/auth/dev/customer-token'), {})
  setCustomer(null)
  assert.deepEqual(authHeaders('/api/feedback'), {})
})

test('写操作权限提示与后端矩阵一致', () => {
  setStaff({ token: 't', username: 'r', role: 'reviewer' })
  assert.equal(missingPermission('/api/review/3/approve'), null)
  assert.equal(missingPermission('/api/kb/staging/approve'), null)
  assert.match(missingPermission('/api/jobs/kb-build'), /需要管理员/)
  assert.match(missingPermission('/api/kb/vectorize'), /审核员/)

  setStaff({ token: 't', username: 'a', role: 'agent' })
  assert.match(missingPermission('/api/review/3/publish'), /需要管理员或审核员/)
  assert.equal(hasRole('reviewer'), false)

  setStaff({ token: 't', username: 'root', role: 'admin' })
  assert.equal(missingPermission('/api/jobs/kb-build'), null)
  assert.equal(hasRole('reviewer'), true)
  setStaff(null)
})
