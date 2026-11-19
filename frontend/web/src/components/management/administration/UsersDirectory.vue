<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { CurrentUser } from '../../../services/auth'
import {
    createUser,
    getUser,
    listRoles,
    listUsers,
    updateUser,
    updateUserStatus,
    assignUserRole,
    removeUserRole,
    type AccountCategory,
    type Role,
    type User,
    type UserCreateInput,
    type UserFilters,
    type UserProfileUpdateInput,
    type UserStatus,
} from '../../../services/users'

const props = defineProps<{ currentUser: CurrentUser | null }>()

const canCreate = computed(() => props.currentUser?.permissions.includes('user.create') ?? false)
const canUpdate = computed(() => props.currentUser?.permissions.includes('user.update') ?? false)
const canDisable = computed(() => props.currentUser?.permissions.includes('user.disable') ?? false)
const canManageRoles = computed(() => props.currentUser?.permissions.includes('role.update') ?? false)
const canRemoveRoles = ref(false)
const roleActionLoading = ref(false)
const roleActionError = ref('')
const roleActionSuccess = ref('')
const showRoleDialog = ref(false)
const selectedRoleId = ref('')

const users = ref<User[]>([])
const roles = ref<Role[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const statusFilter = ref<'ALL' | UserStatus>('ALL')
const roleFilter = ref('')
const originFilter = ref('ALL')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const totalPages = ref(0)

const activeCount = computed(() => users.value.filter(user => user.status === 'ACTIVE').length)
const disabledCount = computed(() => users.value.filter(user => user.status === 'DISABLED').length)
const isFiltered = computed(() =>
    Boolean(search.value || statusFilter.value !== 'ALL' || roleFilter.value || originFilter.value !== 'ALL'),
)

let searchTimer: ReturnType<typeof setTimeout> | undefined

const showCreateDialog = ref(false)
const creating = ref(false)
const createError = ref('')
const createSuccess = ref('')

const newUser = ref<UserCreateInput>({
    full_name: '',
    email: '',
    initial_password: '',
    account_category: 'DATA_MANAGER',
})

const accountCategories: { value: AccountCategory; label: string }[] = [
    { value: 'PLATFORM_OWNER', label: 'Platform Owner' },
    { value: 'SYSTEM_ADMIN', label: 'System Admin' },
    { value: 'DATA_MANAGER', label: 'Data Manager' },
    { value: 'MANAGEMENT', label: 'Management' },
    { value: 'STEM_COORDINATOR', label: 'STEM Coordinator' },
    { value: 'PARA_TEACHER', label: 'Para Teacher' },
]

const showProfileDialog = ref(false)
const profileLoading = ref(false)
const profileSaving = ref(false)
const profileError = ref('')
const selectedUser = ref<User | null>(null)
const profileForm = ref<UserProfileUpdateInput>({
    full_name: '',
    email: '',
})


const statusUpdating = ref(false)
const statusError = ref('')
const statusSuccess = ref('')

async function toggleUserStatus(user: User) {
    if (!canDisable.value || statusUpdating.value) return

    const nextStatus: UserStatus = user.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'
    const action = nextStatus === 'DISABLED' ? 'disable' : 'enable'

    const confirmed = window.confirm(
        `Are you sure you want to ${action} ${user.full_name} (${user.user_code})?`,
    )

    if (!confirmed) return

    statusUpdating.value = true
    statusError.value = ''
    statusSuccess.value = ''

    try {
        await updateUserStatus(user.id, { status: nextStatus })
        statusSuccess.value = `${user.user_code} was ${nextStatus === 'ACTIVE' ? 'enabled' : 'disabled'} successfully.`
        await loadUsers()
    } catch (reason) {
        statusError.value = reason instanceof Error
            ? reason.message
            : `Unable to ${action} this account.`
    } finally {
        statusUpdating.value = false
    }
}

async function openProfileDialog(user: User) {
    showProfileDialog.value = true
    profileLoading.value = true
    profileError.value = ''
    selectedUser.value = null

    try {
        selectedUser.value = await getUser(user.id)
        profileForm.value = {
            full_name: selectedUser.value.full_name,
            email: selectedUser.value.email,
        }
    } catch (reason) {
        profileError.value = reason instanceof Error
            ? reason.message
            : 'Unable to load user details.'
    } finally {
        profileLoading.value = false
    }
}

function closeProfileDialog() {
    if (profileSaving.value) return
    showProfileDialog.value = false
    selectedUser.value = null
    profileError.value = ''
}

async function saveUserProfile() {
    if (!canUpdate.value || !selectedUser.value || profileSaving.value) return

    const fullName = profileForm.value.full_name?.trim() ?? ''
    const email = profileForm.value.email?.trim() ?? ''

    if (!fullName || !email) {
        profileError.value = 'Full name and email address are required.'
        return
    }

    profileSaving.value = true
    profileError.value = ''

    try {
        await updateUser(selectedUser.value.id, {
            full_name: fullName,
            email,
        })

        showProfileDialog.value = false
        selectedUser.value = null
        createSuccess.value = 'User profile updated successfully.'
        await loadUsers()
    } catch (reason) {
        profileError.value = reason instanceof Error
            ? reason.message
            : 'Unable to update user profile.'
    } finally {
        profileSaving.value = false
    }
}

async function loadUsers() {
    loading.value = true
    error.value = ''

    const filters: UserFilters = {
        page: page.value,
        page_size: pageSize.value,
        search: search.value.trim() || undefined,
        status: statusFilter.value === 'ALL' ? undefined : statusFilter.value,
        role_code: roleFilter.value || undefined,
        data_origin: originFilter.value === 'ALL' ? undefined : originFilter.value as UserFilters['data_origin'],
        sort_by: 'created_at',
        sort_order: 'desc',
    }

    try {
        const result = await listUsers(filters)
        users.value = result.data
        total.value = result.pagination.total
        totalPages.value = result.pagination.total_pages
    } catch (reason) {
        error.value = reason instanceof Error ? reason.message : 'Unable to load users.'
    } finally {
        loading.value = false
    }
}

async function loadRoles() {
    try {
        roles.value = await listRoles()
    } catch {
        // Role filtering is optional; user records remain accessible.
    }
}

async function loadCurrentActorRole() {
    if (!canManageRoles.value || !props.currentUser?.user_id) {
        canRemoveRoles.value = false
        return
    }

    try {
        const actor = await getUser(props.currentUser.user_id)
        canRemoveRoles.value = actor.user_roles.some(
            association =>
                association.is_active &&
                association.role.code === 'PLATFORM_OWNER',
        )
    } catch {
        canRemoveRoles.value = false
    }
}

function openRoleDialog(user: User) {
    if (!canManageRoles.value) return

    selectedUser.value = user
    selectedRoleId.value = ''
    roleActionError.value = ''
    roleActionSuccess.value = ''
    showRoleDialog.value = true
}

function closeRoleDialog() {
    if (roleActionLoading.value) return
    showRoleDialog.value = false
    selectedUser.value = null
    selectedRoleId.value = ''
    roleActionError.value = ''
}

async function handleAssignRole() {
    if (
        !canManageRoles.value ||
        !selectedUser.value ||
        !selectedRoleId.value ||
        roleActionLoading.value
    ) return

    const alreadyAssigned = selectedUser.value.user_roles.some(
        association =>
            association.is_active &&
            association.role_id === selectedRoleId.value,
    )

    if (alreadyAssigned) {
        roleActionError.value = 'This role is already assigned.'
        return
    }

    roleActionLoading.value = true
    roleActionError.value = ''

    try {
        await assignUserRole(selectedUser.value.id, {
            role_id: selectedRoleId.value,
        })

        roleActionSuccess.value = 'Role assigned successfully.'
        selectedUser.value = await getUser(selectedUser.value.id)
        await loadUsers()
    } catch (reason) {
        roleActionError.value = reason instanceof Error
            ? reason.message
            : 'Unable to assign this role.'
    } finally {
        roleActionLoading.value = false
    }
}

async function handleRemoveRole(roleId: string, roleName: string) {
    if (
        !canRemoveRoles.value ||
        !selectedUser.value ||
        roleActionLoading.value
    ) return

    const confirmed = window.confirm(
        `Remove the ${roleName} role from ${selectedUser.value.full_name}?`,
    )

    if (!confirmed) return

    roleActionLoading.value = true
    roleActionError.value = ''

    try {
        await removeUserRole(selectedUser.value.id, roleId)

        roleActionSuccess.value = `${roleName} role removed successfully.`
        selectedUser.value = await getUser(selectedUser.value.id)
        await loadUsers()
    } catch (reason) {
        roleActionError.value = reason instanceof Error
            ? reason.message
            : 'Unable to remove this role.'
    } finally {
        roleActionLoading.value = false
    }
}

function clearFilters() {
    search.value = ''
    statusFilter.value = 'ALL'
    roleFilter.value = ''
    originFilter.value = 'ALL'
    page.value = 1
}

function goToPage(nextPage: number) {
    if (nextPage < 1 || nextPage > totalPages.value || nextPage === page.value) return
    page.value = nextPage
}

function roleNames(user: User) {
    return user.user_roles
        .filter(association => association.is_active)
        .map(association => association.role.name)
        .join(', ') || 'No assigned role'
}

function formatDate(value: string | null) {
    if (!value) return 'Never'
    return new Date(value).toLocaleDateString()
}

function openCreateDialog() {
    createError.value = ''
    createSuccess.value = ''
    newUser.value = {
        full_name: '',
        email: '',
        initial_password: '',
        account_category: 'DATA_MANAGER',
    }
    showCreateDialog.value = true
}

function closeCreateDialog() {
    if (creating.value) return
    showCreateDialog.value = false
    createError.value = ''
}

async function submitCreateUser() {
    if (!canCreate.value || creating.value) return

    createError.value = ''
    createSuccess.value = ''

    const payload: UserCreateInput = {
        full_name: newUser.value.full_name.trim(),
        email: newUser.value.email.trim(),
        initial_password: newUser.value.initial_password,
        account_category: newUser.value.account_category,
    }

    if (!payload.full_name) {
        createError.value = "Enter the user's full name."
        return
    }

    if (!payload.email) {
        createError.value = "Enter the user's email address."
        return
    }

    if (payload.initial_password.length < 12 || payload.initial_password.length > 128) {
        createError.value = 'Initial password must be between 12 and 128 characters.'
        return
    }

    creating.value = true

    try {
        const created = await createUser(payload)
        showCreateDialog.value = false
        createSuccess.value = `User ${created.user_code} was created successfully.`
        page.value = 1
        await loadUsers()
    } catch (reason) {
        createError.value = reason instanceof Error ? reason.message : 'Unable to create user.'
    } finally {
        creating.value = false
    }
}

watch(search, () => {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
        page.value = 1
        void loadUsers()
    }, 350)
})

watch([statusFilter, roleFilter, originFilter, page, pageSize], () => {
    void loadUsers()
})

onMounted(() => {
    void loadUsers()
    void loadRoles()
    void loadCurrentActorRole()
})

onUnmounted(() => {
    if (searchTimer) clearTimeout(searchTimer)
})
</script>


<template>
    <div class="users-directory">
        <p v-if="createSuccess" class="users-success" role="status">
            {{ createSuccess }}
        </p>
        <p v-if="statusSuccess" class="users-success" role="status">
            {{ statusSuccess }}
        </p>

        <p v-if="statusError" class="users-error" role="alert">
            {{ statusError }}
        </p>
        <div v-if="showCreateDialog" class="users-modal-backdrop" @click.self="closeCreateDialog">
            <section class="users-modal" role="dialog" aria-modal="true" aria-labelledby="create-user-title">
                <header class="users-modal-header">
                    <div>
                        <p class="users-eyebrow">Administration</p>
                        <h3 id="create-user-title">Create user account</h3>
                    </div>
                    <button class="users-secondary" type="button" :disabled="creating" @click="closeCreateDialog">
                        Cancel
                    </button>
                </header>

                <form class="users-create-form" @submit.prevent="submitCreateUser">
                    <label>
                        Full name
                        <input v-model="newUser.full_name" type="text" maxlength="150" required autocomplete="name"
                            placeholder="Enter full name" />
                    </label>

                    <label>
                        Email address
                        <input v-model="newUser.email" type="email" required autocomplete="email"
                            placeholder="name@example.com" />
                    </label>

                    <label>
                        Account category
                        <select v-model="newUser.account_category" required>
                            <option v-for="category in accountCategories" :key="category.value" :value="category.value">
                                {{ category.label }}
                            </option>
                        </select>
                    </label>

                    <label>
                        Initial password
                        <input v-model="newUser.initial_password" type="password" minlength="12" maxlength="128"
                            required autocomplete="new-password" placeholder="At least 12 characters" />
                        <small>Must contain between 12 and 128 characters.</small>
                    </label>

                    <p v-if="createError" class="users-error" role="alert">
                        {{ createError }}
                    </p>

                    <footer class="users-modal-actions">
                        <button class="users-secondary" type="button" :disabled="creating" @click="closeCreateDialog">
                            Cancel
                        </button>
                        <button class="users-primary" type="submit" :disabled="creating">
                            {{ creating ? 'Creating…' : 'Create user' }}
                        </button>
                    </footer>
                </form>
            </section>
        </div>

        <div v-if="showProfileDialog" class="users-modal-backdrop" @click.self="closeProfileDialog">
            <section class="users-modal" role="dialog" aria-modal="true" aria-labelledby="user-profile-title">
                <header class="users-modal-header">
                    <div>
                        <p class="users-eyebrow">Administration</p>
                        <h3 id="user-profile-title">
                            {{ canUpdate ? 'User profile' : 'User details' }}
                        </h3>
                    </div>
                    <button class="users-secondary" type="button" :disabled="profileSaving" @click="closeProfileDialog">
                        Close
                    </button>
                </header>

                <p v-if="profileLoading" class="users-muted">
                    Loading user details…
                </p>

                <template v-else-if="selectedUser">
                    <div class="users-profile-details">
                        <p><strong>User code</strong><span>{{ selectedUser.user_code }}</span></p>
                        <p><strong>Account category</strong><span>{{ selectedUser.account_category.replaceAll('_', ' ')
                                }}</span></p>
                        <p><strong>Status</strong><span>{{ selectedUser.status }}</span></p>
                        <p><strong>Data origin</strong><span>{{ selectedUser.data_origin }}</span></p>
                        <p><strong>Assigned roles</strong><span>{{ roleNames(selectedUser) }}</span></p>
                        <p><strong>Last login</strong><span>{{ formatDate(selectedUser.last_login_at) }}</span></p>
                        <p><strong>Created</strong><span>{{ formatDate(selectedUser.created_at) }}</span></p>
                    </div>

                    <form v-if="canUpdate" class="users-create-form" @submit.prevent="saveUserProfile">
                        <label>
                            Full name
                            <input v-model="profileForm.full_name" type="text" maxlength="150" required />
                        </label>

                        <label>
                            Email address
                            <input v-model="profileForm.email" type="email" required />
                        </label>

                        <p v-if="profileError" class="users-error" role="alert">
                            {{ profileError }}
                        </p>

                        <footer class="users-modal-actions">
                            <button class="users-primary" type="submit" :disabled="profileSaving">
                                {{ profileSaving ? 'Saving…' : 'Save changes' }}
                            </button>
                        </footer>
                    </form>

                    <p v-else-if="profileError" class="users-error" role="alert">
                        {{ profileError }}
                    </p>
                </template>

                <p v-else-if="profileError" class="users-error" role="alert">
                    {{ profileError }}
                </p>
            </section>
        </div>
        <div v-if="showRoleDialog" class="users-modal-backdrop" @click.self="closeRoleDialog">
            <section class="users-modal" role="dialog" aria-modal="true" aria-labelledby="user-roles-title">
                <header class="users-modal-header">
                    <div>
                        <p class="users-eyebrow">Administration</p>
                        <h3 id="user-roles-title">Manage user roles</h3>
                        <p v-if="selectedUser" class="users-muted">
                            {{ selectedUser.full_name }} · {{ selectedUser.user_code }}
                        </p>
                    </div>
                    <button class="users-secondary" type="button" :disabled="roleActionLoading"
                        @click="closeRoleDialog">
                        Close
                    </button>
                </header>

                <template v-if="selectedUser">
                    <div class="users-profile-details">
                        <p>
                            <strong>Assigned roles</strong>
                            <span>{{ roleNames(selectedUser) }}</span>
                        </p>
                    </div>

                    <form class="users-create-form" @submit.prevent="handleAssignRole">
                        <label>
                            Assign role
                            <select v-model="selectedRoleId" required>
                                <option value="" disabled>Select a role</option>
                                <option v-for="role in roles.filter(
                                    item => canRemoveRoles || item.code !== 'PLATFORM_OWNER'
                                )" :key="role.id" :value="role.id" :disabled="selectedUser.user_roles.some(
        association => association.is_active && association.role_id === role.id
    )">
                                    {{ role.name }}
                                </option>
                            </select>
                        </label>

                        <button class="users-primary" type="submit" :disabled="roleActionLoading || !selectedRoleId">
                            {{ roleActionLoading ? 'Processing…' : 'Assign role' }}
                        </button>
                    </form>

                    <div v-if="canRemoveRoles" class="users-role-removal">
                        <h4>Remove assigned roles</h4>
                        <div v-for="association in selectedUser.user_roles.filter(item => item.is_active)"
                            :key="association.id" class="users-role-row">
                            <span>{{ association.role.name }}</span>
                            <button class="users-link" type="button" :disabled="roleActionLoading"
                                @click="handleRemoveRole(association.role_id, association.role.name)">
                                Remove
                            </button>
                        </div>
                    </div>

                    <p v-if="roleActionSuccess" class="users-success" role="status">
                        {{ roleActionSuccess }}
                    </p>

                    <p v-if="roleActionError" class="users-error" role="alert">
                        {{ roleActionError }}
                    </p>
                </template>
            </section>
        </div>
        <header class="users-header">
            <div>
                <p class="users-eyebrow">Administration</p>
                <h2>Users Directory</h2>
                <p>Manage user accounts and review their assigned roles.</p>
            </div>
            <button v-if="canCreate" class="users-primary" type="button" @click="openCreateDialog">
                <span class="material-symbols-outlined" aria-hidden="true">person_add</span>
                Add user
            </button>
        </header>

        <section class="users-summary" aria-label="User summary">
            <article class="users-card">
                <span>Matching users</span>
                <strong>{{ total }}</strong>
                <small>Based on current filters</small>
            </article>
            <article class="users-card">
                <span>Active on this page</span>
                <strong>{{ activeCount }}</strong>
                <small>Current page</small>
            </article>
            <article class="users-card">
                <span>Disabled on this page</span>
                <strong>{{ disabledCount }}</strong>
                <small>Current page</small>
            </article>
            <article class="users-card">
                <span>Page</span>
                <strong>{{ totalPages ? page : 0 }} / {{ totalPages }}</strong>
                <small>{{ pageSize }} records per page</small>
            </article>
        </section>

        <section class="users-panel" aria-labelledby="users-directory-title">
            <div class="users-panel-heading">
                <div>
                    <p class="users-eyebrow">Directory</p>
                    <h3 id="users-directory-title">User accounts</h3>
                </div>
                <button class="users-secondary" type="button" :disabled="!isFiltered" @click="clearFilters">
                    Clear filters
                </button>
            </div>

            <div class="users-filters">
                <label>
                    Search
                    <input v-model="search" type="search" placeholder="User code, name or email" />
                </label>
                <label>
                    Role
                    <select v-model="roleFilter">
                        <option value="">All roles</option>
                        <option v-for="role in roles" :key="role.id" :value="role.code">{{ role.name }}</option>
                    </select>
                </label>
                <label>
                    Status
                    <select v-model="statusFilter">
                        <option value="ALL">All statuses</option>
                        <option value="ACTIVE">Active</option>
                        <option value="DISABLED">Disabled</option>
                    </select>
                </label>
                <label>
                    Data origin
                    <select v-model="originFilter">
                        <option value="ALL">All origins</option>
                        <option value="PRODUCTION">Production</option>
                        <option value="DEMO">Demo</option>
                        <option value="TEST">Test</option>
                    </select>
                </label>
            </div>

            <p v-if="error" class="users-error" role="alert">
                {{ error }}
                <button class="users-link" type="button" @click="loadUsers">Retry</button>
            </p>

            <p v-if="loading" class="users-muted" role="status">Loading users…</p>

            <div v-else-if="!users.length" class="users-empty">
                {{ isFiltered ? 'No users match the selected filters.' : 'No user records are available.' }}
            </div>

            <div v-else class="users-table-wrap">
                <p class="users-scroll-hint">
                    Swipe horizontally to view all user details and actions →
                </p>
                <table class="users-table">
                    <thead>
                        <tr>
                            <th class="users-frozen">User code</th>
                            <th>Name</th>
                            <th>Email</th>
                            <th>Account category</th>
                            <th>Assigned roles</th>
                            <th>Status</th>
                            <th>Origin</th>
                            <th>Last login</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="user in users" :key="user.id">
                            <td class="users-frozen"><strong>{{ user.user_code }}</strong></td>
                            <td>{{ user.full_name }}</td>
                            <td>{{ user.email }}</td>
                            <td>{{ user.account_category.replaceAll('_', ' ') }}</td>
                            <td>{{ roleNames(user) }}</td>
                            <td>
                                <span class="users-status" :class="`is-${user.status.toLowerCase()}`">
                                    {{ user.status }}
                                </span>
                            </td>
                            <td><span class="users-origin">{{ user.data_origin }}</span></td>
                            <td>{{ formatDate(user.last_login_at) }}</td>
                            <td class="users-actions">
                                <button class="users-link" type="button" @click="openProfileDialog(user)">
                                    View
                                </button>

                                <button v-if="canUpdate" class="users-link" type="button"
                                    @click="openProfileDialog(user)">
                                    Edit
                                </button>
                                <button v-if="canManageRoles" class="users-link" type="button"
                                    @click="openRoleDialog(user)">
                                    Roles
                                </button>
                                <button v-if="canDisable" class="users-link" type="button" :disabled="statusUpdating"
                                    @click="toggleUserStatus(user)">
                                    {{ user.status === 'ACTIVE' ? 'Disable' : 'Enable' }}
                                </button>
                                <span v-if="!canUpdate && !canManageRoles && !canDisable" class="users-muted">View
                                    only</span>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <footer class="users-pagination">
                <label>
                    Rows
                    <select v-model.number="pageSize">
                        <option :value="10">10</option>
                        <option :value="20">20</option>
                        <option :value="50">50</option>
                        <option :value="100">100</option>
                    </select>
                </label>
                <span>{{ total ? (page - 1) * pageSize + 1 : 0 }}–{{ Math.min(page * pageSize, total) }} of {{ total
                }}</span>
                <div>
                    <button class="users-secondary" type="button" :disabled="page <= 1 || loading"
                        @click="goToPage(page - 1)">
                        Previous
                    </button>
                    <button class="users-secondary" type="button" :disabled="page >= totalPages || loading"
                        @click="goToPage(page + 1)">
                        Next
                    </button>
                </div>
            </footer>
        </section>
    </div>
</template>

<style scoped>
.users-success {
    margin: 0;
    padding: 12px 14px;
    border-radius: 8px;
    color: var(--ov-tag-accent-fg);
    background: var(--ov-tag-accent-bg);
}

.users-modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: grid;
    place-items: center;
    padding: 20px;
    background: rgb(0 0 0 / 45%);
}

.users-modal {
    width: min(100%, 520px);
    max-height: min(90vh, 760px);
    overflow-y: auto;
    padding: 24px;
    border: 1px solid var(--ov-border);
    border-radius: 14px;
    background: var(--ov-bg-surface);
    box-shadow: 0 20px 60px rgb(0 0 0 / 20%);
}

.users-modal-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 22px;
}

.users-modal-header h3 {
    margin: 0;
    color: var(--ov-text-primary);
}

.users-create-form {
    display: grid;
    gap: 16px;
}

.users-role-removal {
    display: grid;
    gap: 12px;
    margin-top: 22px;
}

.users-role-removal h4 {
    margin: 0;
    color: var(--ov-text-primary);
    font-size: 14px;
}

.users-role-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid var(--ov-border-subtle);
    color: var(--ov-text-primary);
    font-size: 13px;
}

.users-profile-details {
    display: grid;
    gap: 0;
    margin-bottom: 20px;
}

.users-profile-details p {
    display: grid;
    grid-template-columns: minmax(120px, 1fr) 1.5fr;
    gap: 12px;
    margin: 0;
    padding: 11px 0;
    border-bottom: 1px solid var(--ov-border-subtle);
    color: var(--ov-text-primary);
    font-size: 13px;
}

.users-profile-details strong {
    color: var(--ov-text-muted);
}

.users-profile-details span {
    overflow-wrap: anywhere;
}

@media (max-width: 480px) {
    .users-profile-details p {
        grid-template-columns: 1fr;
        gap: 4px;
    }
}

.users-create-form label {
    display: grid;
    gap: 7px;
    color: var(--ov-text-secondary);
    font-size: 13px;
    font-weight: 600;
}

.users-create-form input,
.users-create-form select {
    box-sizing: border-box;
    width: 100%;
    padding: 11px 12px;
    border: 1px solid var(--ov-border);
    border-radius: 6px;
    background: var(--ov-bg-page);
    color: var(--ov-text-primary);
    font: inherit;
}

.users-create-form small {
    color: var(--ov-text-muted);
    font-weight: 400;
}

.users-modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    padding-top: 8px;
}

@media (max-width: 600px) {
    .users-modal {
        padding: 18px;
    }

    .users-modal-actions {
        flex-wrap: wrap;
    }
}

.users-directory {
    display: grid;
    gap: 20px;
}

.users-header,
.users-panel-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
}

.users-header h2,
.users-panel h3 {
    margin: 0;
    color: var(--ov-text-primary);
}

.users-header h2 {
    font-size: 30px;
}

.users-header p:last-child,
.users-muted {
    margin: 6px 0 0;
    color: var(--ov-text-muted);
}

.users-eyebrow {
    margin: 0 0 4px;
    color: var(--ov-brand);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .08em;
}

.users-summary {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
}

.users-card,
.users-panel {
    padding: 20px;
    border: 1px solid var(--ov-border);
    border-radius: 12px;
    background: var(--ov-bg-surface);
}

.users-card {
    display: grid;
    gap: 6px;
}

.users-card span,
.users-card small {
    color: var(--ov-text-muted);
    font-size: 12px;
}

.users-card strong {
    color: var(--ov-text-primary);
    font-size: 28px;
}

.users-panel {
    display: grid;
    gap: 20px;
}

.users-filters {
    display: grid;
    grid-template-columns: minmax(220px, 1.5fr) repeat(3, minmax(140px, 1fr));
    gap: 12px;
}

.users-filters label,
.users-pagination label {
    display: grid;
    gap: 6px;
    color: var(--ov-text-secondary);
    font-size: 13px;
}

.users-filters input,
.users-filters select,
.users-pagination select {
    box-sizing: border-box;
    width: 100%;
    padding: 10px;
    border: 1px solid var(--ov-border);
    border-radius: 6px;
    background: var(--ov-bg-page);
    color: var(--ov-text-primary);
}

.users-table-wrap {
    width: 100%;
    max-width: 100%;
    min-width: 0;
    overflow-x: auto;
    overflow-y: hidden;
    overscroll-behavior-x: contain;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: thin;
}

.users-table {
    width: 100%;
    min-width: 1100px;
    border-collapse: collapse;
    color: var(--ov-text-primary);
    font-size: 13px;
}

.users-table th,
.users-table td {
    padding: 13px 10px;
    border-bottom: 1px solid var(--ov-border-subtle);
    text-align: left;
    white-space: nowrap;
}

.users-table th {
    color: var(--ov-text-muted);
    font-size: 11px;
    text-transform: uppercase;
}

.users-frozen {
    position: sticky;
    left: 0;
    z-index: 1;
    background: var(--ov-bg-surface);
}

.users-status,
.users-origin {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 11px;
}

.users-status.is-active {
    color: var(--ov-tag-accent-fg);
    background: var(--ov-tag-accent-bg);
}

.users-status.is-disabled,
.users-origin {
    color: var(--ov-text-muted);
    background: var(--ov-bg-surface-subtle);
}

.users-actions {
    display: flex;
    gap: 12px;
}

.users-link {
    padding: 0;
    border: 0;
    background: none;
    color: var(--ov-brand);
    cursor: pointer;
    font-weight: 600;
}

.users-link:disabled {
    cursor: not-allowed;
    opacity: .5;
}

.users-primary,
.users-secondary {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    border: 0;
    border-radius: 6px;
    padding: 10px 14px;
    cursor: pointer;
    font-weight: 600;
}

.users-primary {
    color: var(--ov-button-primary-text);
    background: var(--ov-brand);
}

.users-primary:disabled,
.users-secondary:disabled {
    cursor: not-allowed;
    opacity: .55;
}

.users-secondary {
    color: var(--ov-text-primary);
    background: var(--ov-bg-surface-subtle);
}

.users-empty {
    padding: 28px;
    color: var(--ov-text-muted);
    text-align: center;
    background: var(--ov-bg-surface-subtle);
    border-radius: 8px;
}

.users-error {
    margin: 0;
    color: var(--ov-tag-terra-fg);
}

.users-pagination {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 16px;
    color: var(--ov-text-muted);
    font-size: 13px;
}

.users-pagination label {
    display: flex;
    align-items: center;
}

.users-pagination select {
    width: 75px;
}

.users-pagination div {
    display: flex;
    gap: 8px;
}

@media (max-width: 1000px) {
    .users-summary {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .users-filters {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 600px) {

    .users-header,
    .users-panel-heading {
        flex-direction: column;
    }

    .users-summary,
    .users-filters {
        grid-template-columns: 1fr;
    }

    .users-card,
    .users-panel {
        padding: 16px;
    }

    .users-pagination {
        flex-wrap: wrap;
        justify-content: space-between;
    }
}

.users-scroll-hint {
    display: none;
    margin: 0 0 8px;
    color: var(--ov-text-muted);
    font-size: 12px;
}

@media (max-width: 600px) {
    .users-scroll-hint {
        display: block;
    }
}
</style>
