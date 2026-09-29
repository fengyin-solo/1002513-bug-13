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
        <input v-model="filters.keyword" placeholder="按信号机编号检索" />
      </label>
      <label class="filter-item">
        <span>信号机状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item filter-check">
        <input v-model="repairableOnly" type="checkbox" />
        <span>只看可维修范围（维修入口，已停用除外）</span>
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
            <span
              v-if="column === '灯泡寿命'"
              :class="{ 'life-expired': Number(row['寿命剩余天数']) <= 0 }"
              :title="lifeTitle(row)"
            >{{ row[column] ?? '—' }}</span>
            <span v-else-if="column === '显示距离'" :title="row['显示距离说明'] ?? ''">
              {{ row[column] ?? '—' }}
              <em v-if="row['显示距离说明']" class="note-mark" title="显示距离缺失，沿用原有数据">注</em>
            </span>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
            <button class="link" type="button" @click="openConfig(row)">改灯位配置</button>
            <template v-if="row['可维修']">
              <button class="link" type="button" @click="openBroken(row)">登记断丝</button>
              <button
                v-if="row['信号机状态'] !== '维修中'"
                class="link"
                type="button"
                @click="runAction('安排维修', row, {})"
              >安排维修</button>
              <button class="link danger" type="button" @click="runAction('办理停用', row, {})">办理停用</button>
            </template>
            <span v-else class="muted-text">已停用，不在维修范围</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无信号机数据，可先登记信号机</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条信号机记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 断丝登记 -->
    <div v-if="brokenModal.open" class="modal-mask" @click.self="brokenModal.open = false">
      <div class="modal-card">
        <h3>登记断丝 · {{ brokenModal.row?.['信号机编号'] }}</h3>
        <label class="form-row">
          <span>断丝灯位</span>
          <input v-model="brokenModal.lamp" placeholder="例如：红灯位" />
        </label>
        <label class="form-row">
          <span>点灯单元</span>
          <input v-model="brokenModal.unit" placeholder="可选，留空沿用原登记" />
        </label>
        <p class="form-hint">同一灯位重复登记只更新原记录，不会新增重复条目。</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="brokenModal.open = false">取消</button>
          <button class="btn primary" type="button" @click="submitBroken">提交登记</button>
        </div>
      </div>
    </div>

    <!-- 改动灯位配置 -->
    <div v-if="configModal.open" class="modal-mask" @click.self="configModal.open = false">
      <div class="modal-card">
        <h3>改动灯位配置 · {{ configModal.row?.['信号机编号'] }}</h3>
        <label class="form-row">
          <span>灯位配置</span>
          <input v-model="configModal.form['灯位配置']" placeholder="例如：红、黄、绿、引导白" />
        </label>
        <label class="form-row">
          <span>显示距离</span>
          <input v-model="configModal.form['显示距离']" :placeholder="`当前：${configModal.row?.['显示距离'] ?? '未登记'}，留空保留原值`" />
        </label>
        <label class="form-row">
          <span>点灯单元</span>
          <input v-model="configModal.form['点灯单元']" placeholder="留空保留原值" />
        </label>
        <p class="form-hint">显示距离留空时后端保留原有数据，并在详情中给出说明。</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="configModal.open = false">取消</button>
          <button class="btn primary" type="button" @click="submitConfig">保存配置</button>
        </div>
      </div>
    </div>

    <!-- 单条详情：数据与列表来自同一接口口径 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal-card detail-card">
        <h3>信号机详情 · {{ detail['信号机编号'] }}</h3>
        <dl class="detail-grid">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detail[column] ?? '—' }}</dd>
          </template>
          <dt>寿命剩余天数</dt>
          <dd :class="{ 'life-expired': Number(detail['寿命剩余天数']) <= 0 }">
            {{ detail['寿命剩余天数'] === null ? '—' : `${detail['寿命剩余天数']} 天（到期当天按到期处理）` }}
          </dd>
          <dt>是否可维修</dt>
          <dd>{{ detail['可维修'] ? '在维修范围内' : '已停用，不参与维修' }}</dd>
          <template v-if="detail['显示距离说明']">
            <dt>显示距离说明</dt>
            <dd>{{ detail['显示距离说明'] }}</dd>
          </template>
        </dl>
        <h4>断丝登记记录（按灯位去重）</h4>
        <table class="data-table">
          <thead>
            <tr><th>灯位</th><th>点灯单元</th><th>登记时间</th></tr>
          </thead>
          <tbody>
            <tr v-for="record in detail['断丝登记'] ?? []" :key="record['灯位']">
              <td>{{ record['灯位'] }}</td>
              <td>{{ record['点灯单元'] || '—' }}</td>
              <td>{{ record['登记时间'] }}</td>
            </tr>
            <tr v-if="!(detail['断丝登记'] ?? []).length">
              <td colspan="3" class="empty-state">暂无断丝登记</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/signal'
const columns = ["信号机编号", "所属车站", "信号机类型", "灯位配置", "显示距离", "灯泡寿命", "点灯单元", "信号机状态"]
const statuses = ["正常", "主灯丝断", "维修中", "已停用"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = reactive<Record<string, string>>({ keyword: '', status: '' })
const repairableOnly = ref(false)
const stats = ref<{ label: string; value: number }[]>([
  { label: '正常信号机', value: 0 },
  { label: '断丝信号机', value: 0 },
  { label: '维修中信号机', value: 0 },
  { label: '已停用信号机', value: 0 },
  { label: '可维修信号机', value: 0 },
])

const detail = ref<Row | null>(null)
const brokenModal = reactive<{ open: boolean; row: Row | null; lamp: string; unit: string }>({
  open: false,
  row: null,
  lamp: '',
  unit: '',
})
const configModal = reactive<{ open: boolean; row: Row | null; form: Record<string, string> }>({
  open: false,
  row: null,
  form: {},
})

function lifeTitle(row: Row) {
  const remaining = row['寿命剩余天数']
  if (remaining === null || remaining === undefined) return ''
  return Number(remaining) <= 0 ? '灯泡已到期，需更换' : `剩余 ${remaining} 天`
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  repairableOnly.value = false
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '信号机登记入口尚未接入审批流'
}

function openBroken(row: Row) {
  brokenModal.open = true
  brokenModal.row = row
  brokenModal.lamp = ''
  brokenModal.unit = ''
}

async function submitBroken() {
  if (!brokenModal.row) return
  await runAction('登记断丝', brokenModal.row, { 灯位: brokenModal.lamp, 点灯单元: brokenModal.unit })
  if (!errorMessage.value) brokenModal.open = false
}

function openConfig(row: Row) {
  configModal.open = true
  configModal.row = row
  configModal.form = {
    灯位配置: String(row['灯位配置'] ?? ''),
    显示距离: '',
    点灯单元: '',
  }
}

async function submitConfig() {
  if (!configModal.row) return
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${configModal.row.id}/config`, {
      method: 'PUT',
      body: JSON.stringify(configModal.form),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? '灯位配置未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? '灯位配置已更新'
    configModal.open = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '灯位配置更新失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('信号机详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '信号机详情读取失败'
  }
}

async function runAction(action: string, row: Row, extra: Record<string, string>) {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (action === '登记断丝' && !extra['灯位']?.trim()) {
    errorMessage.value = '请填写断丝灯位后再提交'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action, ...extra }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? '信号机动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? '操作已生效'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '信号机操作失败'
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats/summary`)
    if (!response.ok) return
    const data = await response.json()
    stats.value = [
      { label: '正常信号机', value: data['正常'] ?? 0 },
      { label: '断丝信号机', value: data['主灯丝断'] ?? 0 },
      { label: '维修中信号机', value: data['维修中'] ?? 0 },
      { label: '已停用信号机', value: data['已停用'] ?? 0 },
      { label: '可维修信号机', value: data['可维修'] ?? 0 },
    ]
  } catch {
    // 统计失败不阻塞列表使用
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.status) query.set('status', filters.status)
  if (repairableOnly.value) query.set('scope', 'repairable')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('信号机列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '信号机列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.filter-check {
  display: flex;
  align-items: center;
  gap: 6px;
}
.filter-check input {
  margin: 0;
}
.life-expired {
  color: #b42318;
  font-weight: 600;
}
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.notice-text {
  color: #1f6feb;
}
.note-mark {
  color: #b45309;
  font-style: normal;
  font-size: 11px;
  border: 1px solid #b45309;
  border-radius: 3px;
  padding: 0 3px;
  margin-left: 4px;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  background: #fff;
  border-radius: 8px;
  padding: 18px 20px;
  width: 420px;
  max-width: calc(100vw - 32px);
}
.detail-card {
  width: 720px;
  max-height: 85vh;
  overflow: auto;
}
.modal-card h3 {
  margin: 0 0 14px;
}
.modal-card h4 {
  margin: 16px 0 8px;
}
.form-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.form-row span {
  width: 64px;
  font-size: 13px;
  color: var(--muted);
}
.form-row input {
  flex: 1;
}
.form-hint {
  font-size: 12px;
  color: var(--muted);
  margin: 4px 0 12px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 6px 12px;
  margin: 0 0 8px;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
</style>
