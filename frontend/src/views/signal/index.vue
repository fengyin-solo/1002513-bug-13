<template>
  <section class="page" data-module="signal">
    <header class="page-head">
      <div>
        <h2>信号机管理</h2>
        <p class="page-desc">维护信号机，围绕信号机编号、所属车站、信号机类型、灯位配置做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记信号机</button>
        <button class="btn" type="button" @click="exportRows">导出信号机清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>信号机编号</span>
        <input v-model="keyword" placeholder="按信号机编号检索" />
      </label>
      <label class="filter-item">
        <span>信号机状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item filter-check">
        <input v-model="maintainableOnly" type="checkbox" />
        <span>仅看可维修（排除已停用）</span>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '灯泡寿命'">
              <span>{{ row['灯泡寿命'] || '—' }}</span>
              <span v-if="row['剩余天数'] !== null && row['剩余天数'] !== ''" :class="lifeClass(row['剩余天数'])">
                （剩余{{ row['剩余天数'] }}天{{ lifeHint(row['剩余天数']) }}）
              </span>
            </template>
            <template v-else-if="column === '信号机状态'">
              <span :class="['status-tag', statusClass(row.status)]">{{ row.status ?? '—' }}</span>
            </template>
            <template v-else>{{ row[column] || '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <template v-if="row.status !== '已停用'">
              <button class="link" type="button" @click="openConfig(row)">修改灯位配置</button>
              <button class="link" type="button" @click="openBroken(row)">登记断丝</button>
              <button class="link" type="button" @click="runAction('安排维修', row)">安排维修</button>
              <button class="link" type="button" @click="runAction('办理停用', row)">办理停用</button>
            </template>
            <span v-else class="muted-text">已停用，不在可维修范围</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无信号机数据，可先登记信号机</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条信号机记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="infoMessage" class="info-text">{{ infoMessage }}</span>
    </footer>

    <div v-if="detailRow" class="modal-mask" @click.self="detailRow = null">
      <div class="modal">
        <h3>信号机明细 · {{ detailRow['信号机编号'] }}</h3>
        <dl class="detail-grid">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd v-if="column === '信号机状态'">
              <span :class="['status-tag', statusClass(detailRow.status)]">{{ detailRow.status }}</span>
            </dd>
            <dd v-else-if="column === '灯泡寿命'">
              {{ detailRow['灯泡寿命'] || '—' }}
              <span v-if="detailRow['剩余天数'] !== null && detailRow['剩余天数'] !== ''" :class="lifeClass(detailRow['剩余天数'])">
                剩余{{ detailRow['剩余天数'] }}天{{ lifeHint(detailRow['剩余天数']) }}
              </span>
            </dd>
            <dd v-else>{{ detailRow[column] || '—' }}</dd>
          </template>
        </dl>
        <h4>断丝登记记录</h4>
        <table v-if="brokenRecords(detailRow).length" class="data-table inner-table">
          <thead>
            <tr><th>灯位</th><th>点灯单元</th></tr>
          </thead>
          <tbody>
            <tr v-for="(record, index) in brokenRecords(detailRow)" :key="index">
              <td>{{ record['灯位'] }}</td>
              <td>{{ record['点灯单元'] || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted-text">暂无断丝登记记录</p>
        <div class="modal-foot">
          <button class="btn" type="button" @click="detailRow = null">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="configOpen" class="modal-mask" @click.self="configOpen = false">
      <div class="modal">
        <h3>修改灯位配置 · {{ configForm['信号机编号'] }}</h3>
        <p class="muted-text">显示距离、灯泡寿命、点灯单元留空时保留原有数据。</p>
        <form class="modal-form" @submit.prevent="submitConfig">
          <label>
            <span>灯位配置 *</span>
            <input v-model="configForm['灯位配置']" placeholder="如：红、黄、绿" />
          </label>
          <label>
            <span>显示距离</span>
            <input v-model="configForm['显示距离']" placeholder="留空保留原值，如：800m" />
          </label>
          <label>
            <span>灯泡寿命（到期日）</span>
            <input v-model="configForm['灯泡寿命']" type="date" />
          </label>
          <label>
            <span>点灯单元</span>
            <input v-model="configForm['点灯单元']" placeholder="留空保留原值，如：DDX-01" />
          </label>
          <div class="modal-foot">
            <button class="btn" type="button" @click="configOpen = false">取消</button>
            <button class="btn primary" type="submit">保存配置</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="brokenOpen" class="modal-mask" @click.self="brokenOpen = false">
      <div class="modal">
        <h3>登记断丝 · {{ brokenForm['信号机编号'] }}</h3>
        <p class="muted-text">同一灯位重复登记只会保留一条记录。</p>
        <form class="modal-form" @submit.prevent="submitBroken">
          <label>
            <span>灯位</span>
            <input v-model="brokenForm['灯位']" placeholder="如：主灯丝" />
          </label>
          <label>
            <span>点灯单元</span>
            <input v-model="brokenForm['点灯单元']" placeholder="如：DDX-01" />
          </label>
          <div class="modal-foot">
            <button class="btn" type="button" @click="brokenOpen = false">取消</button>
            <button class="btn primary" type="submit">确认登记</button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type BrokenRecord = { 灯位: string; 点灯单元?: string }
type Row = {
  id: number | string
  status?: string
  [key: string]: unknown
}

const ENDPOINT = '/api/signal'
const columns = ["信号机编号", "所属车站", "信号机类型", "灯位配置", "显示距离", "灯泡寿命", "点灯单元", "信号机状态"]
const statuses = ["正常", "主灯丝断", "维修中", "已停用"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const infoMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const maintainableOnly = ref(false)

const detailRow = ref<Row | null>(null)
const configOpen = ref(false)
const configForm = reactive<Record<string, string>>({})
const brokenOpen = ref(false)
const brokenForm = reactive<Record<string, string>>({})

const stats = computed(() => [
  { label: "正常信号机", value: countByStatus("正常") },
  { label: "断丝信号机", value: countByStatus("主灯丝断") },
  { label: "维修中信号机", value: countByStatus("维修中") },
  { label: "可维修信号机", value: rows.value.filter((row) => row.status !== "已停用").length },
])

function countByStatus(status: string): number {
  return rows.value.filter((row) => row.status === status).length
}

function brokenRecords(row: Row | null): BrokenRecord[] {
  const value = row?.['断丝记录']
  return Array.isArray(value) ? (value as BrokenRecord[]) : []
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  maintainableOnly.value = false
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '信号机登记入口尚未接入审批流'
}

function statusClass(status: unknown): string {
  return {
    正常: 'status-ok',
    主灯丝断: 'status-abnormal',
    维修中: 'status-doing',
    已停用: 'status-off',
  }[String(status)] ?? 'status-ok'
}

function lifeClass(days: unknown): string {
  const value = Number(days)
  if (value < 0) return 'life-overdue'
  if (value === 0) return 'life-due'
  if (value <= 7) return 'life-soon'
  return 'life-ok'
}

function lifeHint(days: unknown): string {
  const value = Number(days)
  if (value < 0) return '，已逾期，请尽快更换'
  if (value === 0) return '，今日到期'
  return ''
}

function openDetail(row: Row) {
  detailRow.value = row
}

function syncDetailRow(latest: Row[]) {
  if (!detailRow.value) return
  detailRow.value = latest.find((row) => String(row.id) === String(detailRow.value?.id)) ?? null
}

function openConfig(row: Row) {
  configForm.id = String(row.id)
  for (const key of ["信号机编号", "灯位配置", "显示距离", "灯泡寿命", "点灯单元"]) {
    configForm[key] = String(row[key] ?? '')
  }
  configOpen.value = true
}

async function submitConfig() {
  errorMessage.value = ''
  infoMessage.value = ''
  const lamp = configForm['灯位配置'].trim()
  if (!lamp) {
    errorMessage.value = '灯位配置为必填项，请填写后再提交'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${configForm.id}/config`, {
      method: 'PUT',
      body: JSON.stringify({
        values: {
          '灯位配置': lamp,
          '显示距离': configForm['显示距离'],
          '灯泡寿命': configForm['灯泡寿命'],
          '点灯单元': configForm['点灯单元'],
        },
      }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message ?? '灯位配置未保存'
      return
    }
    infoMessage.value = payload.message
    configOpen.value = false
    await reload()
  } catch {
    errorMessage.value = '灯位配置保存失败'
  }
}

function openBroken(row: Row) {
  brokenForm.id = String(row.id)
  brokenForm['信号机编号'] = String(row['信号机编号'] ?? '')
  brokenForm['灯位'] = '主灯丝'
  brokenForm['点灯单元'] = String(row['点灯单元'] ?? '')
  brokenOpen.value = true
}

async function submitBroken() {
  const lamp = brokenForm['灯位'].trim()
  if (!lamp) {
    errorMessage.value = '请填写断丝灯位'
    return
  }
  await sendAction('登记断丝', brokenForm.id, {
    灯位: lamp,
    点灯单元: brokenForm['点灯单元'],
  })
  if (!errorMessage.value) {
    brokenOpen.value = false
  }
}

async function runAction(action: string, row: Row) {
  await sendAction(action, String(row.id), {})
}

async function sendAction(action: string, entryId: string, extra: Record<string, string>) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...extra } }),
    })
    if (!response.ok) {
      throw new Error('信号机动作未生效，请稍后重试')
    }
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message ?? '信号机操作失败'
      return
    }
    infoMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '信号机操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  infoMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
  if (statusFilter.value) params.set('status', statusFilter.value)
  if (maintainableOnly.value) params.set('maintainable', 'true')
  params.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('信号机列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    syncDetailRow(rows.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '信号机列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.status-tag { padding: 1px 8px; border-radius: 10px; font-size: 12px; white-space: nowrap; }
.status-ok { background: #e7f6ec; color: #18794e; }
.status-abnormal { background: #fde8e8; color: #b42318; }
.status-doing { background: #fef3c7; color: #92400e; }
.status-off { background: #e2e8f0; color: #475569; }
.life-ok { color: #18794e; font-size: 12px; }
.life-soon { color: #92400e; font-size: 12px; }
.life-due { color: #b42318; font-size: 12px; font-weight: 600; }
.life-overdue { color: #b42318; font-size: 12px; font-weight: 600; }
.muted-text { color: var(--muted); font-size: 12px; }
.info-text { color: #1f6feb; }
.filter-check { display: flex; align-items: center; gap: 6px; }
.filter-check input { margin: 0; }
.modal-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center; z-index: 20;
}
.modal {
  background: #fff; border-radius: 8px; padding: 18px 20px;
  width: 560px; max-width: calc(100vw - 32px); max-height: 82vh; overflow: auto;
}
.modal h3 { margin: 0 0 8px; font-size: 16px; }
.modal h4 { margin: 14px 0 6px; font-size: 14px; }
.modal-form { display: flex; flex-direction: column; gap: 10px; margin-top: 8px; }
.modal-form label span, .detail-grid dt { display: block; font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.modal-form input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.detail-grid { display: grid; grid-template-columns: 110px 1fr 110px 1fr; gap: 6px 10px; margin: 8px 0; }
.detail-grid dt { color: var(--muted); font-size: 12px; }
.detail-grid dd { margin: 0; font-size: 13px; }
.inner-table { margin-top: 4px; }
</style>
