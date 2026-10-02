// 登录状态：员工令牌与顾客令牌分开保存在 sessionStorage，关闭标签页即失效。
// 所有接口请求都经过 authFetch：按路径带上对应令牌，收到 401 时清掉令牌并通知页面跳转登录。
import { reactive } from 'vue'

export type Role = 'admin' | 'reviewer' | 'agent'
export interface StaffSession {
  token: string
  username: string
  role: Role
}

const STAFF_KEY = 'assistflow-staff'
const CUSTOMER_KEY = 'assistflow-customer'
export const AUTH_EXPIRED_EVENT = 'assistflow:auth-expired'

// 顾客接口：身份来自电商主站签发的顾客令牌
const CUSTOMER_PATHS = ['/api/graph-chat', '/api/actions', '/api/conversations', '/api/feedback']
// 无需令牌的接口
const PUBLIC_PATHS = ['/api/health', '/api/auth/login', '/api/auth/config', '/api/auth/dev/']

export const ROLE_NAMES: Record<Role, string> = { admin: '管理员', reviewer: '审核员', agent: '坐席' }

function read<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function write(key: string, value: unknown) {
  try {
    if (value == null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 隐私模式等场景写不进去时，仅在本页内存中保持登录
  }
}

export const session = reactive<{ staff: StaffSession | null; customer: { token: string; userId: string } | null }>({
  staff: read(STAFF_KEY),
  customer: read(CUSTOMER_KEY),
})

export function setStaff(value: StaffSession | null) {
  session.staff = value
  write(STAFF_KEY, value)
}

export function setCustomer(value: { token: string; userId: string } | null) {
  session.customer = value
  write(CUSTOMER_KEY, value)
}

export const isCustomerPath = (path: string) => CUSTOMER_PATHS.some((p) => path.startsWith(p))
const isPublicPath = (path: string) => PUBLIC_PATHS.some((p) => path.startsWith(p))

/** 角色是否满足；管理员总是满足。按钮据此置灰，最终以后端 403 为准。 */
export function hasRole(...roles: Role[]) {
  const role = session.staff?.role
  return !!role && (role === 'admin' || roles.includes(role))
}

// 与后端权限矩阵一致的写操作要求（只用于提前提示，最终以后端 403 为准）
const WRITE_ROLES: [RegExp, Role[]][] = [
  [/^\/api\/(kb\/(preview|ingest|vectorize)|jobs\/|knowledge\/evaluate)/, []],
  [/^\/api\/(review\/|kb\/staging\/(approve|reject))/, ['reviewer']],
  [/^\/api\/agent\//, ['agent']],
]

/** 当前员工执行该写操作缺少权限时返回提示文字，否则返回 null。 */
export function missingPermission(path: string): string | null {
  const rule = WRITE_ROLES.find(([pattern]) => pattern.test(path))
  if (!rule || hasRole(...rule[1])) return null
  const need = ['管理员', ...rule[1].map((r) => ROLE_NAMES[r])].join('或')
  return `当前账号（${session.staff ? ROLE_NAMES[session.staff.role] : '未登录'}）没有执行此操作的权限，需要${need}。`
}

export function authHeaders(path: string): Record<string, string> {
  if (isPublicPath(path)) return {}
  const token = isCustomerPath(path) ? session.customer?.token : session.staff?.token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = { ...(init.headers as Record<string, string> | undefined), ...authHeaders(path) }
  const response = await fetch(path, { ...init, headers })
  if (response.status === 401 && !isPublicPath(path)) {
    const kind = isCustomerPath(path) ? 'customer' : 'staff'
    if (kind === 'staff') setStaff(null)
    else setCustomer(null)
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail: { kind } }))
  }
  return response
}
