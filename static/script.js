const API_BASE = '/api';
let jwtToken = localStorage.getItem('zpwx_jwt');
let isAdmin = localStorage.getItem('zpwx_is_admin') === 'true';
let isSuperAdmin = localStorage.getItem('zpwx_is_super_admin') === 'true';
let currentUserId = localStorage.getItem('zpwx_current_user_id');
let currentAccountId = null;
let selectedAccounts = new Set();
let historyPage = 1;
let logsPage = 1;
let allAccounts = [];

document.addEventListener('DOMContentLoaded', function() {
    checkAuth();
    initEventListeners();
});

function initEventListeners() {
    document.getElementById('verify-form').addEventListener('submit', handleVerify);
    document.getElementById('step-form').addEventListener('submit', handleSetStep);
    
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const tabName = this.dataset.tab;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
            document.getElementById(tabName + '-tab').style.display = 'block';
            
            if (tabName === 'history') loadHistory();
            if (tabName === 'tasks') loadTasks();
        });
    });
}

function checkAuth() {
    if (jwtToken) {
        showMainPage();
    } else {
        showVerifyPage();
    }
}

function showVerifyPage() {
    document.getElementById('verify-card').style.display = 'block';
    document.getElementById('main-card').style.display = 'none';
}

function showMainPage() {
    document.getElementById('verify-card').style.display = 'none';
    document.getElementById('main-card').style.display = 'block';
    loadAccounts();
    if (isAdmin) {
        document.getElementById('admin-section').style.display = 'block';
        loadCodes();
    } else {
        document.getElementById('admin-section').style.display = 'none';
    }
}

function togglePassword() {
    const input = document.getElementById('verify-code');
    const btn = document.querySelector('.toggle-password');
    const eyeOpen = btn.querySelector('.eye-open');
    const eyeClosed = btn.querySelector('.eye-closed');
    
    if (input.type === 'password') {
        input.type = 'text';
        btn.classList.add('show-password');
        eyeOpen.style.display = 'none';
        eyeClosed.style.display = 'block';
    } else {
        input.type = 'password';
        btn.classList.remove('show-password');
        eyeOpen.style.display = 'block';
        eyeClosed.style.display = 'none';
    }
}

function toggleAccountPassword() {
    const input = document.getElementById('account-password');
    const btn = document.querySelector('#add-account-modal .toggle-password');
    const eyeOpen = btn.querySelector('.eye-open');
    const eyeClosed = btn.querySelector('.eye-closed');
    
    if (input.type === 'password') {
        input.type = 'text';
        btn.classList.add('show-password');
        eyeOpen.style.display = 'none';
        eyeClosed.style.display = 'block';
    } else {
        input.type = 'password';
        btn.classList.remove('show-password');
        eyeOpen.style.display = 'block';
        eyeClosed.style.display = 'none';
    }
}

async function handleVerify(e) {
    e.preventDefault();

    const code = document.getElementById('verify-code').value.trim();

    if (!code) {
        showResult('verify-result', '请输入验证码', 'error');
        return;
    }

    try {
        showLoading('verify-btn', true);
        hideResult('verify-result');

        const response = await fetch(`${API_BASE}/verify-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await response.json();

        if (data.success) {
            jwtToken = data.token;
            isAdmin = data.isAdmin || false;
            isSuperAdmin = data.isSuperAdmin || false;

            const payload = parseJwt(jwtToken);
            const currentUserId = payload.user_id;
            localStorage.setItem('zpwx_jwt', jwtToken);
            localStorage.setItem('zpwx_is_admin', isAdmin);
            localStorage.setItem('zpwx_is_super_admin', isSuperAdmin);
            localStorage.setItem('zpwx_current_user_id', currentUserId);

            showMainPage();
        } else {
            showResult('verify-result', data.error, 'error');
        }
    } catch (error) {
        showResult('verify-result', '验证失败: ' + error.message, 'error');
    } finally {
        showLoading('verify-btn', false);
    }
}

function logout() {
    jwtToken = null;
    isAdmin = false;
    isSuperAdmin = false;
    currentAccountId = null;
    selectedAccounts.clear();
    localStorage.removeItem('zpwx_jwt');
    localStorage.removeItem('zpwx_is_admin');
    localStorage.removeItem('zpwx_is_super_admin');
    localStorage.removeItem('zpwx_current_user_id');
    checkAuth();
}

function parseJwt(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        return JSON.parse(jsonPayload);
    } catch (e) {
        return {};
    }
}

async function loadAccounts() {
    try {
        const response = await fetch(`${API_BASE}/accounts`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ action: 'list' })
        });
        const data = await response.json();

        if (data.error) {
            if (data.error.includes('认证') || data.error.includes('别处登录')) {
                alert(data.error);
                logout();
            }
            return;
        }

        allAccounts = data.accounts || [];
        renderAccounts(allAccounts);
        updateAccountFilter(allAccounts);
        updateTaskAccountSelect(allAccounts);
    } catch (error) {
        console.error('加载账号失败:', error);
    }
}

function renderAccounts(accounts) {
    const list = document.getElementById('accounts-list');
    const stepSection = document.getElementById('step-section');

    if (accounts.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                </svg>
                <p>暂未添加账号</p>
                <button class="btn btn-outline" onclick="showAddAccountModal()">添加第一个账号</button>
            </div>
        `;
        stepSection.style.display = 'none';
        return;
    }

    list.innerHTML = accounts.map(acc => `
        <div class="account-item ${currentAccountId === acc.id ? 'selected' : ''}">
            <div class="account-checkbox">
                <input type="checkbox" id="acc-${acc.id}" value="${acc.id}" ${selectedAccounts.has(acc.id) ? 'checked' : ''} onchange="handleAccountSelect(${acc.id}, event)">
            </div>
            <div class="account-item-info" onclick="selectAccount(${acc.id}, '${formatUserDisplay(acc.user)}')">
                <div class="account-item-avatar">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                        <circle cx="12" cy="7" r="4"/>
                    </svg>
                </div>
                <span class="account-item-name">${formatUserDisplay(acc.user)}</span>
            </div>
            <button class="account-item-delete" onclick="event.stopPropagation(); deleteAccount(${acc.id})">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
            </button>
        </div>
    `).join('');

    if (currentAccountId) {
        const selected = accounts.find(a => a.id === currentAccountId);
        if (selected) {
            stepSection.style.display = 'block';
            document.getElementById('selected-account-name').textContent = formatUserDisplay(selected.user);
        }
    }
}

function formatUserDisplay(user) {
    if (!user) return '';
    if (user.includes('@')) {
        return user[0] + '***' + user.substring(user.indexOf('@'));
    }
    return user.substring(0, 3) + '****' + user.substring(user.length - 4);
}

function selectAccount(id, userDisplay) {
    const checkbox = document.getElementById(`acc-${id}`);
    if (checkbox && checkbox.checked) {
        checkbox.checked = false;
        selectedAccounts.delete(id);
    }
    currentAccountId = id;
    document.getElementById('selected-count-num').textContent = selectedAccounts.size;
    updateBatchActions();
    document.getElementById('selected-account-name').textContent = userDisplay;
    document.getElementById('step-section').style.display = 'block';
    document.getElementById('step').value = '';
    hideResult('main-result');
    renderAccounts(allAccounts);
}

function handleAccountSelect(id, event) {
    event.stopPropagation();
    event.preventDefault();
    const checkbox = document.getElementById(`acc-${id}`);
    if (checkbox) {
        if (checkbox.checked) {
            selectedAccounts.add(id);
        } else {
            selectedAccounts.delete(id);
        }
    }
    document.getElementById('selected-count-num').textContent = selectedAccounts.size;
    updateBatchActions();
}

function updateBatchActions() {
    const batchActions = document.querySelector('.batch-actions');
    if (selectedAccounts.size > 0) {
        batchActions.style.display = 'flex';
    } else {
        batchActions.style.display = 'none';
    }
}

function updateAccountFilter(accounts) {
    const filter = document.getElementById('history-account-filter');
    filter.innerHTML = '<option value="">全部账号</option>' + 
        accounts.map(acc => `<option value="${acc.id}">${formatUserDisplay(acc.user)}</option>`).join('');
}

function updateTaskAccountSelect(accounts) {
    const select = document.getElementById('task-account');
    select.innerHTML = '<option value="">请选择账号</option>' + 
        accounts.map(acc => `<option value="${acc.id}">${formatUserDisplay(acc.user)}</option>`).join('');
}

function showAddAccountModal() {
    document.getElementById('add-account-modal').style.display = 'flex';
    document.getElementById('account-user').value = '';
    document.getElementById('account-password').value = '';
    hideResult('add-account-result');
    document.getElementById('account-user').focus();
}

function hideAddAccountModal() {
    document.getElementById('add-account-modal').style.display = 'none';
}

async function addAccount() {
    const user = document.getElementById('account-user').value.trim();
    const password = document.getElementById('account-password').value;

    if (!user || !password) {
        showResult('add-account-result', '请输入账号和密码', 'error');
        return;
    }

    try {
        showLoading('add-account-btn', true);
        hideResult('add-account-result');

        const response = await fetch(`${API_BASE}/accounts`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ action: 'add', user, password })
        });
        const data = await response.json();

        if (data.success) {
            hideAddAccountModal();
            currentAccountId = data.account.id;
            loadAccounts();
        } else {
            if (data.error.includes('别处登录')) {
                alert(data.error);
                logout();
                return;
            }
            showResult('add-account-result', data.error, 'error');
        }
    } catch (error) {
        showResult('add-account-result', '添加失败: ' + error.message, 'error');
    } finally {
        showLoading('add-account-btn', false);
    }
}

async function deleteAccount(id) {
    if (!confirm('确定删除该账号吗？')) return;

    try {
        const response = await fetch(`${API_BASE}/account/delete`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ id })
        });
        const data = await response.json();

        if (data.success) {
            if (currentAccountId === id) {
                currentAccountId = null;
                document.getElementById('step-section').style.display = 'none';
            }
            selectedAccounts.delete(id);
            document.getElementById('selected-count-num').textContent = selectedAccounts.size;
            updateBatchActions();
            loadAccounts();
        }
    } catch (error) {
        console.error('删除账号失败:', error);
    }
}

function setStep(value) {
    document.getElementById('step').value = value;
}

async function handleSetStep(e) {
    e.preventDefault();

    if (!currentAccountId) {
        showResult('main-result', '请先选择账号', 'error');
        return;
    }

    const step = document.getElementById('step').value.trim();

    if (!step || parseInt(step) < 0) {
        showResult('main-result', '请输入有效的步数', 'error');
        return;
    }

    try {
        showLoading('set-step-btn', true);
        hideResult('main-result');

        const response = await fetch(`${API_BASE}/set-step`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({
                accountId: currentAccountId,
                step
            })
        });
        const data = await response.json();

        if (data.success) {
            showResult('main-result', data.message, 'success');
            document.getElementById('step').value = '';
        } else {
            if (data.error.includes('别处登录')) {
                alert(data.error);
                logout();
                return;
            }
            showResult('main-result', data.error, 'error');
        }
    } catch (error) {
        showResult('main-result', '设置步数失败: ' + error.message, 'error');
    } finally {
        showLoading('set-step-btn', false);
    }
}

async function loadCodes() {
    try {
        const response = await fetch(`${API_BASE}/admin/codes`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ action: 'list' })
        });
        const data = await response.json();

        if (data.error) {
            if (data.error.includes('别处登录')) {
                alert(data.error);
                logout();
            }
            return;
        }

        renderCodes(data.codes || []);
    } catch (error) {
        console.error('加载验证码失败:', error);
    }
}

function renderCodes(codes) {
    const list = document.getElementById('codes-list');

    if (codes.length === 0) {
        list.innerHTML = '<p style="text-align:center;color:#999;">暂无验证码</p>';
        return;
    }

    list.innerHTML = codes.map(code => {
            const canDelete = isSuperAdmin ?
                !code.is_super_admin : !code.is_admin;
            const canReset = isAdmin && code.id != currentUserId && canDelete;

        return `
        <div class="code-item" data-user-id="${code.id}" data-code="${code.code}">
            <div class="code-item-info">
                <span class="code-item-value">${code.code}</span>
                ${code.is_super_admin ? '<span class="code-item-badge super-admin">超级管理员</span>' : ''}
                <span class="code-item-badge ${code.is_admin ? 'admin' : ''}">${code.is_admin ? '管理员' : '普通'}</span>
            </div>
            <div class="code-item-actions">
                ${canReset ? `
                    <button class="code-item-action" onclick="showResetCodeModal(${code.id})" title="重置验证码">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M23 4v6h-6M1 20v-6h6"/>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                        </svg>
                    </button>
                ` : ''}
                ${canDelete ? `
                    <button class="code-item-delete" onclick="deleteCode(${code.id})">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="18" y1="6" x2="6" y2="18"/>
                            <line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                    </button>
                ` : ''}
            </div>
        </div>
        `;
    }).join('');
}

function showAddCodeModal() {
    document.getElementById('add-code-modal').style.display = 'flex';
    document.getElementById('code-value').value = '';

    const adminOptionGroup = document.getElementById('admin-option-group');
    const adminCheckbox = document.getElementById('code-is-admin');

    if (isSuperAdmin) {
        adminOptionGroup.style.display = 'block';
        adminCheckbox.disabled = false;
        adminCheckbox.checked = false;
    } else {
        adminOptionGroup.style.display = 'none';
        adminCheckbox.disabled = true;
        adminCheckbox.checked = false;
    }

    hideResult('add-code-result');
    document.getElementById('code-value').focus();
}

function hideAddCodeModal() {
    document.getElementById('add-code-modal').style.display = 'none';
}

function showChangeCodeModal() {
    document.getElementById('change-code-modal').style.display = 'flex';
    document.getElementById('old-code').value = '';
    document.getElementById('new-code').value = '';
    hideResult('change-code-result');
    document.getElementById('old-code').focus();
}

function hideChangeCodeModal() {
    document.getElementById('change-code-modal').style.display = 'none';
}

async function changeOwnCode() {
    const oldCode = document.getElementById('old-code').value.trim();
    const newCode = document.getElementById('new-code').value.trim();

    if (!oldCode || !newCode) {
        showResult('change-code-result', '请输入旧验证码和新验证码', 'error');
        return;
    }

    if (newCode.length > 16 || newCode.length < 1) {
        showResult('change-code-result', '验证码必须是1-16位任意字符', 'error');
        return;
    }

    try {
        showLoading('change-code-btn', true);
        hideResult('change-code-result');

        const response = await fetch(`${API_BASE}/code/change`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ oldCode, newCode })
        });
        const data = await response.json();

        if (data.success) {
            hideChangeCodeModal();
            alert('验证码修改成功，请重新登录');
            logout();
        } else {
            showResult('change-code-result', data.error, 'error');
        }
    } catch (error) {
        showResult('change-code-result', '修改失败: ' + error.message, 'error');
    } finally {
        showLoading('change-code-btn', false);
    }
}

let resetCodeTargetId = null;
let resetCodeTargetCode = null;

function showResetCodeModal(userId) {
    const codeItem = document.querySelector(`.code-item[data-user-id="${userId}"]`);
    if (!codeItem) {
        alert('找不到用户信息');
        return;
    }
    
    const targetCode = codeItem.dataset.code;

    resetCodeTargetId = userId;
    resetCodeTargetCode = targetCode;
    
    document.getElementById('reset-code-modal').style.display = 'flex';
    document.getElementById('reset-user-display').value = targetCode;
    document.getElementById('reset-new-code').value = '';
    hideResult('reset-code-result');
    document.getElementById('reset-new-code').focus();
}

function hideResetCodeModal() {
    document.getElementById('reset-code-modal').style.display = 'none';
    resetCodeTargetId = null;
    resetCodeTargetCode = null;
}

async function confirmResetCode() {
    const newCode = document.getElementById('reset-new-code').value.trim();

    if (!newCode) {
        showResult('reset-code-result', '请输入新验证码', 'error');
        return;
    }

    if (newCode.length > 16 || newCode.length < 1) {
        showResult('reset-code-result', '验证码必须是1-16位任意字符', 'error');
        return;
    }

    if (!resetCodeTargetId) {
        showResult('reset-code-result', '用户信息错误', 'error');
        return;
    }

    try {
        showLoading('reset-code-btn', true);
        hideResult('reset-code-result');

        const response = await fetch(`${API_BASE}/admin/code/reset`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ userId: resetCodeTargetId, code: newCode })
        });
        const data = await response.json();

        if (data.success) {
            hideResetCodeModal();
            loadCodes();
        } else {
            showResult('reset-code-result', data.error, 'error');
        }
    } catch (error) {
        showResult('reset-code-result', '重置失败: ' + error.message, 'error');
    } finally {
        showLoading('reset-code-btn', false);
    }
}

async function addCode() {
    const code = document.getElementById('code-value').value.trim();
    const isAdmin = document.getElementById('code-is-admin').checked ? 1 : 0;

    if (!code || code.length > 16 || code.length < 1) {
        showResult('add-code-result', '验证码必须是1-16位任意字符', 'error');
        return;
    }

    try {
        showLoading('add-code-btn', true);
        hideResult('add-code-result');

        const response = await fetch(`${API_BASE}/admin/codes`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ action: 'create', code, isAdmin })
        });
        const data = await response.json();

        if (data.success) {
            hideAddCodeModal();
            loadCodes();
        } else {
            showResult('add-code-result', data.error, 'error');
        }
    } catch (error) {
        showResult('add-code-result', '添加失败: ' + error.message, 'error');
    } finally {
        showLoading('add-code-btn', false);
    }
}

async function deleteCode(id) {
    if (!confirm('确定删除该验证码吗？')) return;

    try {
        const response = await fetch(`${API_BASE}/admin/code/delete`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ id })
        });
        const data = await response.json();

        if (data.success) {
            loadCodes();
        }
    } catch (error) {
        console.error('删除验证码失败:', error);
    }
}

async function loadHistory() {
    try {
        const accountId = document.getElementById('history-account-filter').value;
        
        const response = await fetch(`${API_BASE}/history`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ 
                page: historyPage, 
                pageSize: 20,
                accountId: accountId || undefined
            })
        });
        const data = await response.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        renderHistory(data.history || [], data.total, isAdmin);
        renderPagination('history-pagination', data.page, Math.ceil(data.total / data.pageSize), (page) => {
            historyPage = page;
            loadHistory();
        });
    } catch (error) {
        console.error('加载历史记录失败:', error);
    }
}

function renderHistory(history, total, admin) {
    const list = document.getElementById('history-list');
    const thead = document.getElementById('history-table-head');
    
    if (admin) {
        thead.innerHTML = '<th>用户</th><th>账号</th><th>步数</th><th>类型</th><th>结果</th><th>时间</th>';
    } else {
        thead.innerHTML = '<th>账号</th><th>步数</th><th>类型</th><th>结果</th><th>时间</th>';
    }

    if (history.length === 0) {
        list.innerHTML = '<tr><td colspan="' + (admin ? 6 : 5) + '" style="text-align:center;color:#999;">暂无记录</td></tr>';
        return;
    }

    list.innerHTML = history.map(h => {
        const accountUser = h.account_user ? formatUserDisplay(h.account_user) : '未知';
        const stepType = h.is_random ? '<span class="tag tag-random">随机</span>' : '<span class="tag tag-fixed">固定</span>';
        const resultTag = h.result === 'success' ? '<span class="tag tag-success">成功</span>' : '<span class="tag tag-error">失败</span>';
        const createdAt = h.created_at ? h.created_at.substring(0, 19).replace('T', ' ') : '';
        
        if (admin) {
            return `<tr>
                <td>${h.user_code || '未知'}</td>
                <td>${accountUser}</td>
                <td>${parseInt(h.step_value).toLocaleString()}</td>
                <td>${stepType}</td>
                <td>${resultTag}</td>
                <td>${createdAt}</td>
            </tr>`;
        } else {
            return `<tr>
                <td>${accountUser}</td>
                <td>${parseInt(h.step_value).toLocaleString()}</td>
                <td>${stepType}</td>
                <td>${resultTag}</td>
                <td>${createdAt}</td>
            </tr>`;
        }
    }).join('');
}

async function loadTasks() {
    try {
        const response = await fetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ action: 'list' })
        });
        const data = await response.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        renderTasks(data.tasks || []);
    } catch (error) {
        console.error('加载定时任务失败:', error);
    }
}

function renderTasks(tasks) {
    const list = document.getElementById('tasks-list');
    const empty = document.getElementById('tasks-empty');

    if (tasks.length === 0) {
        list.style.display = 'none';
        empty.style.display = 'block';
        return;
    }

    list.style.display = 'flex';
    empty.style.display = 'none';

    list.innerHTML = tasks.map(task => {
        const accountUser = task.account_user ? formatUserDisplay(task.account_user) : '未知';
        const taskType = task.task_type === 'random' ? '<span class="tag tag-random">随机范围</span>' : '<span class="tag tag-fixed">固定步数</span>';
        const stepDisplay = task.task_type === 'random' ? `${task.step_value} 步` : `${parseInt(task.step_value).toLocaleString()} 步`;
        
        return `
            <div class="task-item ${task.is_active ? '' : 'disabled'}">
                <div class="task-info">
                    <div class="task-account">${accountUser}</div>
                    <div class="task-config">
                        ${taskType}
                        <span class="task-range">${stepDisplay}</span>
                        <span class="task-time">每天 ${task.execution_time}</span>
                    </div>
                </div>
                <div class="task-actions">
                    <label class="switch">
                        <input type="checkbox" ${task.is_active ? 'checked' : ''} onchange="toggleTask(${task.id})">
                        <span class="slider"></span>
                    </label>
                    <button class="btn-icon" onclick="deleteTask(${task.id})">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function showAddTaskModal() {
    if (allAccounts.length === 0) {
        alert('请先添加账号');
        return;
    }
    document.getElementById('add-task-modal').style.display = 'flex';
    document.getElementById('task-account').value = '';
    document.getElementById('task-step-value').value = '';
    document.getElementById('task-step-min').value = '';
    document.getElementById('task-step-max').value = '';
    document.getElementById('task-time').value = '08:00';
    document.querySelector('input[name="taskStepType"][value="fixed"]').checked = true;
    toggleTaskStepType();
}

function hideAddTaskModal() {
    document.getElementById('add-task-modal').style.display = 'none';
}

function toggleTaskStepType() {
    const stepType = document.querySelector('input[name="taskStepType"]:checked').value;
    document.querySelector('.task-fixed-group').style.display = stepType === 'fixed' ? 'block' : 'none';
    document.querySelector('.task-random-group').style.display = stepType === 'random' ? 'block' : 'none';
}

async function createTask() {
    const accountId = document.getElementById('task-account').value;
    const taskType = document.querySelector('input[name="taskStepType"]:checked').value;
    const stepValue = taskType === 'fixed' 
        ? document.getElementById('task-step-value').value.trim()
        : `${document.getElementById('task-step-min').value.trim()}-${document.getElementById('task-step-max').value.trim()}`;
    const executionTime = document.getElementById('task-time').value;

    if (!accountId) {
        alert('请选择账号');
        return;
    }

    if (!stepValue) {
        alert('请输入步数');
        return;
    }

    if (taskType === 'random' && (!document.getElementById('task-step-min').value || !document.getElementById('task-step-max').value)) {
        alert('请输入步数范围');
        return;
    }

    try {
        showLoading('create-task-btn', true);

        const response = await fetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ 
                action: 'create',
                accountId: parseInt(accountId),
                taskType,
                stepValue,
                executionTime
            })
        });
        const data = await response.json();

        if (data.success) {
            hideAddTaskModal();
            loadTasks();
        } else {
            alert(data.error);
        }
    } catch (error) {
        alert('创建任务失败: ' + error.message);
    } finally {
        showLoading('create-task-btn', false);
    }
}

async function toggleTask(taskId) {
    try {
        const response = await fetch(`${API_BASE}/task/toggle`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ id: taskId })
        });
        const data = await response.json();
        if (!data.success) {
            alert(data.error);
            loadTasks();
        }
    } catch (error) {
        console.error('切换任务状态失败:', error);
        loadTasks();
    }
}

async function deleteTask(taskId) {
    if (!confirm('确定删除该定时任务吗？')) return;

    try {
        const response = await fetch(`${API_BASE}/task/delete`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ id: taskId })
        });
        const data = await response.json();

        if (data.success) {
            loadTasks();
        }
    } catch (error) {
        console.error('删除任务失败:', error);
    }
}

function showBatchStepModal() {
    if (selectedAccounts.size === 0) {
        alert('请先选择账号');
        return;
    }
    document.getElementById('batch-step-modal').style.display = 'flex';
    document.getElementById('batch-selected-count').textContent = selectedAccounts.size;
    document.getElementById('batch-step').value = '';
    document.getElementById('step-min').value = '';
    document.getElementById('step-max').value = '';
    document.getElementById('batch-results').style.display = 'none';
    document.querySelector('input[name="stepType"][value="fixed"]').checked = true;
    toggleStepType();
}

function hideBatchStepModal() {
    document.getElementById('batch-step-modal').style.display = 'none';
}

function toggleStepType() {
    const stepType = document.querySelector('input[name="stepType"]:checked').value;
    document.querySelector('.step-fixed-group').style.display = stepType === 'fixed' ? 'block' : 'none';
    document.querySelector('.step-random-group').style.display = stepType === 'random' ? 'block' : 'none';
}

async function executeBatchStep() {
    const stepType = document.querySelector('input[name="stepType"]:checked').value;
    let stepValue;
    
    if (stepType === 'fixed') {
        stepValue = document.getElementById('batch-step').value.trim();
        if (!stepValue) {
            alert('请输入步数');
            return;
        }
    } else {
        const min = document.getElementById('step-min').value.trim();
        const max = document.getElementById('step-max').value.trim();
        if (!min || !max) {
            alert('请输入步数范围');
            return;
        }
        stepValue = `${min}-${max}`;
    }

    try {
        showLoading('batch-step-btn', true);

        const response = await fetch(`${API_BASE}/batch-set-step`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({
                accountIds: [...selectedAccounts],
                stepValue,
                stepType
            })
        });
        const data = await response.json();

        if (data.success) {
            showBatchResults(data.results, data.summary);
        } else {
            alert(data.error);
        }
    } catch (error) {
        alert('批量修改失败: ' + error.message);
    } finally {
        showLoading('batch-step-btn', false);
    }
}

function showBatchResults(results, summary) {
    const container = document.getElementById('batch-results');
    container.style.display = 'block';
    
    container.innerHTML = `
        <h4>修改结果 - ${summary}</h4>
        <div class="results-list">
            ${results.map(r => {
                const account = allAccounts.find(a => a.id === r.accountId);
                const accountName = account ? formatUserDisplay(account.user) : `ID:${r.accountId}`;
                const status = r.result === 'success' 
                    ? `<span class="status success">成功${r.step ? '('+parseInt(r.step).toLocaleString()+')' : ''}</span>`
                    : `<span class="status error">失败</span>`;
                return `<div class="result-item">
                    <span class="account">${accountName}</span>
                    ${status}
                </div>`;
            }).join('')}
        </div>
    `;
}

async function showLogsModal() {
    document.getElementById('logs-modal').style.display = 'flex';
    loadLogs();
}

function hideLogsModal() {
    document.getElementById('logs-modal').style.display = 'none';
}

async function loadLogs() {
    try {
        const action = document.getElementById('log-action-filter').value;
        const date = document.getElementById('log-date-filter').value;
        
        const response = await fetch(`${API_BASE}/admin/logs`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${jwtToken}`
            },
            body: JSON.stringify({ 
                page: logsPage, 
                pageSize: 20,
                action: action || undefined,
                startDate: date || undefined,
                endDate: date || undefined
            })
        });
        const data = await response.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        renderLogs(data.logs || []);
        renderPagination('logs-pagination', data.page, Math.ceil(data.total / data.pageSize), (page) => {
            logsPage = page;
            loadLogs();
        });
    } catch (error) {
        console.error('加载日志失败:', error);
    }
}

function renderLogs(logs) {
    const tbody = document.getElementById('logs-table-body');

    if (logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">暂无记录</td></tr>';
        return;
    }

    const actionMap = {
        'login': '登录',
        'add_account': '添加账号',
        'delete_account': '删除账号',
        'set_step': '修改步数',
        'batch_set_step': '批量修改',
        'create_code': '创建验证码',
        'delete_code': '删除验证码',
        'create_task': '创建任务',
        'delete_task': '删除任务'
    };

    tbody.innerHTML = logs.map(log => `
        <tr>
            <td>${log.created_at ? log.created_at.substring(0, 19).replace('T', ' ') : ''}</td>
            <td>${log.user_code || (log.username ? log.username.substring(0, 8) + '...' : '未知')}</td>
            <td><span class="action-tag">${actionMap[log.action] || log.action}</span></td>
            <td>${log.detail || ''}</td>
            <td>${log.ip_address || ''}</td>
        </tr>
    `).join('');
}

function renderPagination(containerId, current, total, onPageChange) {
    const container = document.getElementById(containerId);
    if (total <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '';
    for (let i = 1; i <= total; i++) {
        if (i === 1 || i === total || (i >= current - 1 && i <= current + 1)) {
            html += `<button class="pagination-btn ${i === current ? 'active' : ''}" onclick="arguments[0]?.stopPropagation() || ${onPageChange.toString().replace(/^function\s*\(\)\s*\{/, ''.replace(/\}\s*$/, ''))}">${i}</button>`;
        } else if (i === current - 2 || i === current + 2) {
            html += '<span style="padding:6px;">...</span>';
        }
    }
    container.innerHTML = html;
    
    container.onclick = function(e) {
        if (e.target.classList.contains('pagination-btn')) {
            const page = parseInt(e.target.textContent);
            onPageChange(page);
        }
    };
}

function showLoading(btnId, loading) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    const btnText = btn.querySelector('.btn-text');
    const btnLoading = btn.querySelector('.btn-loading');

    btn.disabled = loading;
    if (loading) {
        btnText.style.display = 'none';
        btnLoading.style.display = 'flex';
    } else {
        btnText.style.display = 'block';
        btnLoading.style.display = 'none';
    }
}

function showResult(elementId, message, type) {
    const result = document.getElementById(elementId);
    result.textContent = message;
    result.className = 'result ' + type;
    result.style.display = 'block';
}

function hideResult(elementId) {
    const result = document.getElementById(elementId);
    if (result) result.style.display = 'none';
}

document.getElementById('add-account-modal')?.addEventListener('click', function(e) {
    if (e.target === this) hideAddAccountModal();
});

document.getElementById('add-code-modal')?.addEventListener('click', function(e) {
    if (e.target === this) hideAddCodeModal();
});

document.getElementById('batch-step-modal')?.addEventListener('click', function(e) {
    if (e.target === this) hideBatchStepModal();
});

document.getElementById('add-task-modal')?.addEventListener('click', function(e) {
    if (e.target === this) hideAddTaskModal();
});

document.getElementById('logs-modal')?.addEventListener('click', function(e) {
    if (e.target === this) hideLogsModal();
});
