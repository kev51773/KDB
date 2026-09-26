document.addEventListener('DOMContentLoaded', () => {
    // --- Init Sidebar Resizer ---
    const sidebar = document.querySelector('.sidebar');
    const resizer = document.getElementById('sidebarResizer');
    let isResizing = false;

    const savedWidth = localStorage.getItem('kdb_sidebar_width');
    if (savedWidth) {
        sidebar.style.width = `${savedWidth}px`;
    }

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        resizer.classList.add('resizing');
        document.body.style.cursor = 'col-resize';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        let newWidth = e.clientX;
        if (newWidth < 200) newWidth = 200;
        if (newWidth > 700) newWidth = 700;
        sidebar.style.width = `${newWidth}px`;
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            resizer.classList.remove('resizing');
            document.body.style.cursor = '';
            localStorage.setItem('kdb_sidebar_width', parseInt(sidebar.style.width));
        }
    });
    let activeConnectionId = null;
    let connectionsList = [];
    let schemaData = { tables: [], views: [] };
    let editor = null;
    let resultsGrid = null;
    let currentTableMetaData = null; // target table for cell edit
    let confirmedFirstEdit = false;
    let pendingEditData = null; // store edit while confirmation modal is open

    // --- Async sqlglot Autocomplete Hinter ---
    async function kdbSqlHint(cm, callback) {
        const cur = cm.getCursor();
        const index = cm.indexFromPos(cur);
        const sqlText = cm.getValue();
        const token = cm.getTokenAt(cur);
        const rawWord = token.string;

        if (!activeConnectionId) {
            callback({ list: [], from: cur, to: cur });
            return;
        }

        try {
            const res = await apiFetch('/api/query/autocomplete', {
                method: 'POST',
                body: JSON.stringify({
                    connection_id: activeConnectionId,
                    sql_query: sqlText,
                    cursor_pos: index
                })
            });

            const list = (res.suggestions || []).map(s => ({
                text: s.text,
                displayText: s.displayText,
                className: `cm-hint-${s.type}`
            }));

            const startCh = rawWord.match(/[\w\.]/) ? token.start : cur.ch;
            callback({
                list: list,
                from: CodeMirror.Pos(cur.line, startCh),
                to: CodeMirror.Pos(cur.line, cur.ch)
            });
        } catch (e) {
            callback({ list: [], from: cur, to: cur });
        }
    }

    kdbSqlHint.async = true;
    CodeMirror.registerHelper("hint", "sql", kdbSqlHint);

    // --- Init CodeMirror with Autocomplete ---
    const textarea = document.getElementById('sqlEditor');
    editor = CodeMirror.fromTextArea(textarea, {
        mode: 'text/x-sql',
        theme: 'dracula',
        lineNumbers: true,
        indentUnit: 4,
        extraKeys: {
            "Tab": "autocomplete",
            "Ctrl-Space": "autocomplete",
            "Ctrl-Enter": () => runQuery(),
            "Cmd-Enter": () => runQuery()
        },
        hintOptions: {
            tables: {}
        }
    });
    editor.setValue("SELECT * FROM users LIMIT 100;");

    // Auto-trigger completion visual popup while typing letters
    editor.on("inputRead", (cm, change) => {
        if (change.text[0] && change.text[0].match(/[a-zA-Z._]/)) {
            CodeMirror.commands.autocomplete(cm, null, { completeSingle: false });
        }
    });

    // --- Init Tabulator Grid ---
    resultsGrid = new Tabulator("#resultsGrid", {
        layout: "fitColumns",
        placeholder: "No data returned yet. Run a query or select a table from schema.",
        pagination: "local",
        paginationSize: 50,
        paginationSizeSelector: [25, 50, 100, 500],
        columns: [],
        cellEdited: (cell) => handleCellEdited(cell)
    });

    // --- Modals Toggle ---
    const openModal = (id) => document.getElementById(id).classList.add('active');
    const closeModal = (id) => {
        if (id === 'connectionModal' && !activeConnectionId) {
            alert('Please select or test a database connection to proceed.');
            return;
        }
        document.getElementById(id).classList.remove('active');
    };

    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const modal = e.target.closest('.modal');
            if (modal) {
                if (modal.id === 'connectionModal' && !activeConnectionId) {
                    alert('Please select or test a database connection to proceed.');
                    return;
                }
                modal.classList.remove('active');
            }
        });
    });

    // --- API Service Calls ---
    async function apiFetch(url, options = {}) {
        try {
            const res = await fetch(url, {
                headers: { 'Content-Type': 'application/json' },
                ...options
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'API request failed');
            }
            return await res.json();
        } catch (e) {
            console.error(e);
            throw e;
        }
    }

    // --- Connections Management ---
    async function loadConnections() {
        connectionsList = await apiFetch('/api/connections');
        const select = document.getElementById('activeConnectionSelect');
        const savedList = document.getElementById('savedConnList');
        
        select.innerHTML = activeConnectionId 
            ? '<option value="">-- Disconnect (No Active DB) --</option>' 
            : '<option value="" disabled selected>-- Select Active Database --</option>';
        savedList.innerHTML = '';

        const connFilter = (document.getElementById('connSearchInput')?.value || '').trim().toLowerCase();
        const filteredConns = connFilter
            ? connectionsList.filter(c => 
                (c.name || '').toLowerCase().includes(connFilter) || 
                (c.db_type || '').toLowerCase().includes(connFilter) ||
                (c.database || '').toLowerCase().includes(connFilter)
              )
            : connectionsList;

        if (!filteredConns.length) {
            savedList.innerHTML = '<li class="text-muted" style="padding: 12px; font-size: 12px; text-align: center;">No matching connection profiles</li>';
        }

        connectionsList.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = `${c.name} (${c.db_type.toUpperCase()})`;
            select.appendChild(opt);
        });

        filteredConns.forEach(c => {
            const isCurrent = activeConnectionId == c.id;

            const li = document.createElement('li');
            li.className = isCurrent ? 'conn-card active-conn' : 'conn-card';
            li.dataset.id = c.id;
            li.style.cursor = 'pointer';
            li.innerHTML = `
                <div class="conn-card-info">
                    <div class="conn-card-title">
                        <strong>${c.name}</strong>
                    </div>
                    <div class="conn-card-sub text-muted" style="display: flex; align-items: center; gap: 6px; margin-top: 4px;">
                        <span class="badge badge-outline" style="font-size: 9px; text-transform: uppercase; padding: 1px 5px;">${c.db_type}</span>
                        ${c.is_read_only ? '<i class="fa-solid fa-lock text-warning" title="Read-Only" style="font-size: 11px;"></i>' : ''}
                        <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;">${c.database || c.host || ''}</span>
                    </div>
                </div>
            `;

            // Single click: select profile & display details in right pane
            li.addEventListener('click', () => {
                document.querySelectorAll('#savedConnList .conn-card').forEach(el => el.classList.remove('active-conn'));
                li.classList.add('active-conn');
                populateConnForm(c);
            });

            // Double-click profile card to connect immediately
            li.addEventListener('dblclick', () => {
                setActiveConnection(c.id);
                document.getElementById('connectionModal').classList.remove('active');
            });

            savedList.appendChild(li);
        });

        if (activeConnectionId) {
            select.value = activeConnectionId;
        }
    }

    function setActiveConnection(connId) {
        activeConnectionId = connId ? parseInt(connId) : null;
        document.getElementById('activeConnectionSelect').value = activeConnectionId || "";
        const badge = document.getElementById('activeConnBadge');
        const conn = connectionsList.find(c => c.id == activeConnectionId);
        
        if (conn) {
            const roText = conn.is_read_only ? ' 🔒 READ-ONLY' : '';
            badge.textContent = `${conn.name} (${conn.db_type.toUpperCase()})${roText}`;
            badge.className = conn.is_read_only ? 'badge badge-outline text-warning' : 'badge badge-outline text-success';
            loadSchema();
            loadBookmarks();
        } else {
            badge.textContent = 'No DB connected';
            badge.className = 'badge badge-outline';
            document.getElementById('schemaTree').innerHTML = '<div class="empty-hint">Select a connection to load tables</div>';
            loadBookmarks();
        }
    }

    document.getElementById('activeConnectionSelect').addEventListener('change', (e) => {
        setActiveConnection(e.target.value);
    });

    document.getElementById('manageConnBtn').addEventListener('click', () => {
        openModal('connectionModal');
        loadConnections();
    });

    document.getElementById('connSearchInput')?.addEventListener('input', () => {
        loadConnections();
    });

    document.getElementById('browseSqliteBtn')?.addEventListener('click', () => {
        document.getElementById('sqliteFileInput').click();
    });

    document.getElementById('sqliteFileInput')?.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            document.getElementById('connDatabase').value = file.path || file.name;
        }
    });

    document.getElementById('addConnProfileBtn').addEventListener('click', () => {
        document.querySelectorAll('#savedConnList .conn-card').forEach(el => el.classList.remove('active-conn'));
        populateConnForm({});
    });

    function getConnPayload() {
        return {
            id: document.getElementById('connId').value ? parseInt(document.getElementById('connId').value) : null,
            name: document.getElementById('connName').value,
            db_type: document.getElementById('connDbType').value,
            host: document.getElementById('connHost').value || null,
            port: document.getElementById('connPort').value ? parseInt(document.getElementById('connPort').value) : null,
            database: document.getElementById('connDatabase').value,
            username: document.getElementById('connUsername').value || null,
            password: document.getElementById('connPassword').value || null,
            is_read_only: document.getElementById('connReadOnly').checked
        };
    }

    function populateConnForm(conn) {
        document.getElementById('connId').value = conn.id || '';
        document.getElementById('connName').value = conn.name || '';
        document.getElementById('connDbType').value = conn.db_type || 'sqlite';
        document.getElementById('connHost').value = conn.host || '';
        document.getElementById('connPort').value = conn.port || '';
        document.getElementById('connDatabase').value = conn.database || '';
        document.getElementById('connUsername').value = conn.username || '';
        document.getElementById('connPassword').value = '';
        document.getElementById('connReadOnly').checked = !!conn.is_read_only;
        document.getElementById('connTestResult').textContent = '';

        const delBtn = document.getElementById('deleteConnBtn');
        if (delBtn) delBtn.style.display = conn.id ? 'inline-block' : 'none';

        toggleRemoteFields(conn.db_type || 'sqlite');
    }

    document.getElementById('connDbType').addEventListener('change', (e) => {
        toggleRemoteFields(e.target.value);
    });

    function toggleRemoteFields(dbType) {
        const isSqlite = dbType === 'sqlite';
        document.querySelectorAll('.db-remote-field').forEach(el => {
            el.style.display = isSqlite ? 'none' : '';
        });
        document.getElementById('dbNameLabel').textContent = isSqlite ? 'Database File Path *' : 'Database Name *';
    }

    document.getElementById('deleteConnBtn')?.addEventListener('click', async () => {
        const connId = document.getElementById('connId').value;
        if (!connId) return;
        if (confirm('Delete connection profile?')) {
            await apiFetch(`/api/connections/${connId}`, { method: 'DELETE' });
            if (activeConnectionId == connId) setActiveConnection(null);
            await loadConnections();
            populateConnForm({});
        }
    });

    document.getElementById('saveConnBtn')?.addEventListener('click', async () => {
        const resultDiv = document.getElementById('connTestResult');
        resultDiv.textContent = 'Saving connection profile...';
        resultDiv.className = 'test-result-msg';

        const payload = getConnPayload();
        if (!payload.name || !payload.database) {
            resultDiv.textContent = 'Profile Name and Database/File Path are required.';
            resultDiv.className = 'test-result-msg error';
            return;
        }

        try {
            const saveRes = await apiFetch('/api/connections', { method: 'POST', body: JSON.stringify(payload) });
            const savedId = saveRes.id || payload.id;
            resultDiv.textContent = 'Profile saved successfully!';
            resultDiv.className = 'test-result-msg success';
            await loadConnections();
            const savedConn = connectionsList.find(c => c.id == savedId);
            if (savedConn) populateConnForm(savedConn);
        } catch (err) {
            resultDiv.textContent = `Error: ${err.message}`;
            resultDiv.className = 'test-result-msg error';
        }
    });

    document.getElementById('connForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const resultDiv = document.getElementById('connTestResult');
        resultDiv.textContent = 'Testing & saving connection...';
        resultDiv.className = 'test-result-msg';

        const payload = getConnPayload();
        try {
            const testRes = await apiFetch('/api/connections/test', { method: 'POST', body: JSON.stringify(payload) });
            if (testRes.status !== 'success') {
                resultDiv.textContent = `Connection failed: ${testRes.message}`;
                resultDiv.className = 'test-result-msg error';
                return;
            }

            const saveRes = await apiFetch('/api/connections', { method: 'POST', body: JSON.stringify(payload) });
            const savedId = saveRes.id || payload.id;

            await loadConnections();
            if (savedId) {
                setActiveConnection(savedId);
                document.getElementById('connectionModal').classList.remove('active');
            }
        } catch (err) {
            resultDiv.textContent = `Error: ${err.message}`;
            resultDiv.className = 'test-result-msg error';
        }
    });

    document.getElementById('testConnBtn').addEventListener('click', async () => {
        const resultDiv = document.getElementById('connTestResult');
        resultDiv.textContent = 'Testing connection...';
        resultDiv.className = 'test-result-msg';
        
        const payload = getConnPayload();
        payload.name = payload.name || 'Test';

        try {
            const res = await apiFetch('/api/connections/test', { method: 'POST', body: JSON.stringify(payload) });
            resultDiv.textContent = res.message;
            resultDiv.className = res.status === 'success' ? 'test-result-msg success' : 'test-result-msg error';
        } catch (err) {
            resultDiv.textContent = err.message;
            resultDiv.className = 'test-result-msg error';
        }
    });

    // --- Schema Inspection ---
    async function loadSchema() {
        if (!activeConnectionId) return;
        const treeContainer = document.getElementById('schemaTree');
        treeContainer.innerHTML = '<div class="empty-hint">Loading schema...</div>';

        try {
            schemaData = await apiFetch(`/api/schema/${activeConnectionId}`);
            
            // Build autocomplete schema map
            const tablesMap = {};
            schemaData.tables.concat(schemaData.views).forEach(item => {
                tablesMap[item.name] = item.columns.map(c => c.name);
            });
            editor.setOption('hintOptions', { tables: tablesMap });

            renderSchemaTree();
        } catch (err) {
            treeContainer.innerHTML = `<div class="empty-hint text-danger">Error: ${err.message}</div>`;
        }
    }

    document.getElementById('refreshSchemaBtn').addEventListener('click', loadSchema);

    function renderSchemaTree() {
        const filter = document.getElementById('schemaSearchInput').value.toLowerCase();
        const treeContainer = document.getElementById('schemaTree');
        treeContainer.innerHTML = '';

        if (!schemaData.tables.length && !schemaData.views.length) {
            treeContainer.innerHTML = '<div class="empty-hint">No tables or views found</div>';
            return;
        }

        // Tables Folder
        const tablesFolder = createTreeGroup('Tables', 'fa-table-cells', schemaData.tables, filter, true);
        if (tablesFolder) treeContainer.appendChild(tablesFolder);

        // Views Folder
        const viewsFolder = createTreeGroup('Views', 'fa-rectangle-list', schemaData.views, filter, false);
        if (viewsFolder) treeContainer.appendChild(viewsFolder);
    }

    function createTreeGroup(groupTitle, iconClass, items, filter, isTableGroup) {
        const matchingItems = items.filter(item => item.name.toLowerCase().includes(filter));
        if (matchingItems.length === 0) return null;

        const groupDiv = document.createElement('div');
        groupDiv.className = 'folder-container open';
        groupDiv.innerHTML = `
            <div class="folder-header">
                <i class="fa-solid fa-chevron-right toggle-icon"></i>
                <i class="fa-solid ${iconClass} text-primary"></i>
                <strong>${groupTitle} (${matchingItems.length})</strong>
            </div>
            <div class="folder-children"></div>
        `;

        const childrenDiv = groupDiv.querySelector('.folder-children');

        matchingItems.forEach(item => {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'tree-header table-item-header';
            itemDiv.dataset.name = item.name;
            itemDiv.innerHTML = `
                <i class="fa-solid ${isTableGroup ? 'fa-table-cells' : 'fa-rectangle-list'} text-muted"></i>
                <span>${item.name}</span>
                <small class="text-muted ml-auto">${item.columns.length} cols</small>
            `;

            // Single click highlights table item
            itemDiv.addEventListener('click', (e) => {
                document.querySelectorAll('.table-item-header').forEach(el => el.classList.remove('active'));
                itemDiv.classList.add('active');
            });

            // Double click loads query with confirmation if editor contains text
            itemDiv.addEventListener('dblclick', () => {
                const currentSql = editor.getValue().trim();
                const newSql = `SELECT * FROM ${item.name} LIMIT 100;`;

                if (currentSql && currentSql !== newSql) {
                    if (!confirm(`Overwrite current SQL query with 'SELECT * FROM ${item.name}'?`)) {
                        return;
                    }
                }

                editor.setValue(newSql);
                currentTableMetaData = item;
                runQuery();
            });

            childrenDiv.appendChild(itemDiv);
        });

        // Toggle folder open/close
        groupDiv.querySelector('.folder-header').addEventListener('click', () => {
            groupDiv.classList.toggle('open');
        });

        return groupDiv;
    }

    document.getElementById('schemaSearchInput').addEventListener('input', renderSchemaTree);

    // --- Query Runner ---
    async function runQuery() {
        if (!activeConnectionId) {
            alert("Please select or configure an active database connection first.");
            return;
        }

        const sql = editor.getValue().trim();
        if (!sql) return;

        // Auto-detect target table metadata from SQL query text if not set by clicking sidebar
        const tableMatch = sql.match(/(?:from|update|into)\s+([a-zA-Z0-9_]+)/i);
        if (tableMatch) {
            const targetTableName = tableMatch[1];
            currentTableMetaData = (schemaData.tables || []).find(t => t.name.toLowerCase() === targetTableName.toLowerCase()) || null;
        }

        const statsBadge = document.getElementById('execStatsBadge');
        statsBadge.textContent = 'Executing query...';
        statsBadge.style.color = '#f59e0b';

        try {
            const res = await apiFetch('/api/query/execute', {
                method: 'POST',
                body: JSON.stringify({
                    connection_id: activeConnectionId,
                    sql_query: sql,
                    limit: 1000
                })
            });

            if (res.status === 'success') {
                statsBadge.textContent = `⚡ ${res.execution_time_ms} ms | ${res.row_count} row(s)`;
                statsBadge.style.color = '#10b981';

                if (res.returns_rows) {
                    renderGridData(res.columns, res.rows);
                } else {
                    resultsGrid.clearData();
                    resultsGrid.setColumns([]);
                }
            } else {
                statsBadge.textContent = `❌ Error (${res.execution_time_ms} ms)`;
                statsBadge.style.color = '#ef4444';
                alert(`Execution Error:\n${res.error_message}`);
            }
        } catch (err) {
            statsBadge.textContent = '❌ Execution failed';
            statsBadge.style.color = '#ef4444';
            alert(`Query Execution Failed:\n${err.message}`);
        }
    }

    document.getElementById('runQueryBtn').addEventListener('click', runQuery);
    document.getElementById('clearQueryBtn').addEventListener('click', () => editor.setValue(''));

    // --- Data Grid & Cell Editing ---
    function renderGridData(columns, rows) {
        const activeConn = connectionsList.find(c => c.id == activeConnectionId);
        const isConnReadOnly = activeConn && activeConn.is_read_only;

        const gridCols = columns.map(colName => {
            let colType = "";
            let isPk = false;

            if (currentTableMetaData) {
                if (currentTableMetaData.primary_keys && currentTableMetaData.primary_keys.includes(colName)) {
                    isPk = true;
                }
                if (currentTableMetaData.columns) {
                    const colMeta = currentTableMetaData.columns.find(c => c.name.toLowerCase() === colName.toLowerCase());
                    if (colMeta) colType = colMeta.type;
                }
            }

            const headerLabel = isPk ? `🔑 ${colName}` : colName;
            const tooltipText = colType 
                ? `Type: ${colType}${isPk ? ' | Primary Key (Read Only)' : (isConnReadOnly ? ' | Read Only Mode' : '')}` 
                : (isPk ? 'Primary Key (Read Only)' : colName);

            return {
                title: headerLabel,
                field: colName,
                headerTooltip: tooltipText,
                editor: (isPk || isConnReadOnly) ? false : "input", // Disable editing if PK or Read-Only mode!
                headerFilter: "input",
                resizable: true,
                cellEdited: (cell) => handleCellEdited(cell)
            };
        });

        resultsGrid.setColumns(gridCols);
        resultsGrid.setData(rows);
    }

    async function handleCellEdited(cell) {
        const colName = cell.getField();
        const newVal = cell.getValue();
        const oldVal = cell.getOldValue();
        const rowData = cell.getRow().getData();

        if (newVal === oldVal || newVal === undefined) return;

        const sqlText = editor.getValue().trim();
        const tableMatch = sqlText.match(/(?:from|update|into)\s+([a-zA-Z0-9_]+)/i);

        // Auto fallback if currentTableMetaData not set or empty
        if (!currentTableMetaData || !currentTableMetaData.primary_keys || currentTableMetaData.primary_keys.length === 0) {
            if (tableMatch && activeConnectionId) {
                const targetTableName = tableMatch[1];
                try {
                    const freshSchema = await apiFetch(`/api/schema/${activeConnectionId}`);
                    schemaData = freshSchema;
                    currentTableMetaData = (freshSchema.tables || []).find(t => t.name.toLowerCase() === targetTableName.toLowerCase()) || null;
                } catch (e) {
                    console.error("Failed to fetch schema for cell edit:", e);
                }
            }
        }

        // Fallback check if rowData has an 'id' column
        if (!currentTableMetaData || !currentTableMetaData.primary_keys || currentTableMetaData.primary_keys.length === 0) {
            const idKey = Object.keys(rowData).find(k => k.toLowerCase() === 'id');
            if (idKey && tableMatch) {
                currentTableMetaData = {
                    name: tableMatch[1],
                    primary_keys: [idKey]
                };
            } else {
                alert("Cannot auto-update row: Primary key column not detected for this table.");
                cell.restoreOldValue();
                return;
            }
        }

        const pkCol = currentTableMetaData.primary_keys[0];
        // Match case-insensitively in rowData
        const rowDataPkKey = Object.keys(rowData).find(k => k.toLowerCase() === pkCol.toLowerCase()) || pkCol;
        const pkVal = rowData[rowDataPkKey];

        if (pkVal === undefined || pkVal === null) {
            alert(`Primary key '${pkCol}' value is missing in row data.`);
            cell.restoreOldValue();
            return;
        }

        const editPayload = {
            connection_id: activeConnectionId,
            table_name: currentTableMetaData.name,
            pk_column: rowDataPkKey,
            pk_value: pkVal,
            column_name: colName,
            new_value: newVal,
            cellRef: cell
        };

        executeCellUpdate(editPayload);
    }

    async function executeCellUpdate(payload) {
        const statsBadge = document.getElementById('execStatsBadge');
        try {
            const res = await apiFetch('/api/edit/cell', {
                method: 'POST',
                body: JSON.stringify({
                    connection_id: payload.connection_id,
                    table_name: payload.table_name,
                    pk_column: payload.pk_column,
                    pk_value: payload.pk_value,
                    column_name: payload.column_name,
                    new_value: payload.new_value
                })
            });
            statsBadge.textContent = `⚡ Cell updated in DB (${payload.table_name}.${payload.column_name} = '${payload.new_value}')`;
            statsBadge.style.color = '#10b981';
        } catch (err) {
            statsBadge.textContent = `❌ Update failed: ${err.message}`;
            statsBadge.style.color = '#ef4444';
            alert(`Failed to update DB: ${err.message}`);
            if (payload.cellRef) payload.cellRef.restoreOldValue();
        }
    }

    document.getElementById('confirmEditBtn').addEventListener('click', () => {
        confirmedFirstEdit = true;
        closeModal('confirmEditModal');
        if (pendingEditData) {
            executeCellUpdate(pendingEditData);
            pendingEditData = null;
        }
    });

    document.getElementById('cancelEditBtn').addEventListener('click', () => {
        closeModal('confirmEditModal');
        if (pendingEditData && pendingEditData.cellRef) {
            pendingEditData.cellRef.restoreOldValue();
        }
        pendingEditData = null;
    });

    document.getElementById('exportCsvBtn').addEventListener('click', () => {
        resultsGrid.download("csv", "kdb_export.csv");
    });

    document.getElementById('gridSearchInput').addEventListener('keyup', (e) => {
        resultsGrid.setFilter((data) => {
            const query = e.target.value.toLowerCase();
            return Object.values(data).some(val => String(val).toLowerCase().includes(query));
        });
    });

    // --- Bookmarks Management ---
    let bookmarkGroups = [];
    let bookmarksList = [];

    async function loadBookmarks() {
        const connParam = activeConnectionId ? `?connection_id=${activeConnectionId}` : '';
        bookmarkGroups = await apiFetch(`/api/bookmarks/groups${connParam}`);
        bookmarksList = await apiFetch(`/api/bookmarks${connParam}`);
        renderBookmarksTree();
    }

    function renderBookmarksTree() {
        const treeContainer = $('#bookmarksTree');
        const filter = (document.getElementById('bookmarksSearchInput')?.value || '').trim().toLowerCase();
        const treeData = [];

        // Filter bookmarks by Title (Name) and Tags
        const matchingBookmarks = filter
            ? bookmarksList.filter(b => {
                const titleMatch = (b.title || '').toLowerCase().includes(filter);
                const tagsMatch = (b.tags || '').toLowerCase().includes(filter);
                return titleMatch || tagsMatch;
              })
            : bookmarksList;

        // Filter groups (include groups whose name matches or that contain a matching bookmark/subgroup)
        const matchingGroupIds = new Set();
        if (filter) {
            bookmarkGroups.forEach(g => {
                if ((g.name || '').toLowerCase().includes(filter)) {
                    matchingGroupIds.add(g.id);
                }
            });
            matchingBookmarks.forEach(b => {
                let gId = b.group_id;
                while (gId) {
                    matchingGroupIds.add(gId);
                    const parentGroup = bookmarkGroups.find(g => g.id === gId);
                    gId = parentGroup ? parentGroup.parent_id : null;
                }
            });
            Array.from(matchingGroupIds).forEach(id => {
                const gObj = bookmarkGroups.find(g => g.id === id);
                let gId = gObj ? gObj.parent_id : null;
                while (gId) {
                    matchingGroupIds.add(gId);
                    const parentGroup = bookmarkGroups.find(g => g.id === gId);
                    gId = parentGroup ? parentGroup.parent_id : null;
                }
            });
        }

        const filteredGroups = filter
            ? bookmarkGroups.filter(g => matchingGroupIds.has(g.id))
            : bookmarkGroups;

        // Build groups (folders)
        filteredGroups.forEach(g => {
            const parentId = g.parent_id ? `group_${g.parent_id}` : '#';
            treeData.push({
                id: `group_${g.id}`,
                parent: parentId,
                text: `<span><i class="fa-solid fa-folder" style="color: ${g.color}"></i> ${g.name}</span>`,
                type: 'folder',
                state: { opened: true },
                data: { isGroup: true, rawId: g.id }
            });
        });

        // Build bookmarks (files)
        matchingBookmarks.forEach(b => {
            const parentId = b.group_id ? `group_${b.group_id}` : '#';
            const notesText = b.notes ? ` <small class="text-muted">(${b.notes})</small>` : '';
            treeData.push({
                id: `bm_${b.id}`,
                parent: parentId,
                text: `<span><i class="fa-solid fa-star text-warning"></i> ${b.title}${notesText}</span>`,
                type: 'bookmark',
                icon: false,
                data: { isBookmark: true, rawId: b.id, sql: b.sql_query, connId: b.connection_id }
            });
        });

        // Destroy previous instance if exists
        if (treeContainer.jstree(true)) {
            treeContainer.jstree(true).destroy();
        }

        if (!treeData.length) {
            if (filter) {
                treeContainer.html('<div class="empty-hint" style="padding: 15px;">No matching bookmarks found</div>');
            } else {
                treeContainer.html('<div class="empty-hint" style="padding: 20px; cursor: pointer;">No bookmarks. Right-click here or click "+ Group" to create one.</div>');
            }
        } else {
            // Initialize jsTree
            treeContainer.jstree({
                core: {
                    data: treeData,
                    check_callback: function(operation, node, node_parent, node_position, more) {
                        if (operation === 'move_node') {
                            if (node_parent.type === 'bookmark') return false;
                        }
                        return true;
                    },
                    animation: 150
                },
                types: {
                    folder: { valid_children: ['folder', 'bookmark'] },
                    bookmark: { valid_children: [] }
                },
                contextmenu: {
                    select_node: true,
                    show_at_node: false,
                    items: function(node) {
                        const isGroup = node.data && node.data.isGroup;
                        const isBookmark = node.data && node.data.isBookmark;
                        const rawId = node.data ? node.data.rawId : null;

                        const items = {};

                        if (isGroup) {
                            items.edit = {
                                label: "Edit",
                                icon: "fa-solid fa-pen",
                                action: function() {
                                    const groupObj = bookmarkGroups.find(g => g.id === rawId);
                                    if (!groupObj) return;
                                    openGroupModal(null, groupObj);
                                }
                            };
                            items.duplicate = {
                                label: "Duplicate",
                                icon: "fa-solid fa-copy",
                                action: function() {
                                    apiFetch(`/api/bookmarks/groups/${rawId}/duplicate`, { method: 'POST' }).then(() => loadBookmarks());
                                }
                            };
                            items.delete = {
                                label: "Delete",
                                icon: "fa-solid fa-trash",
                                action: function() {
                                    const groupObj = bookmarkGroups.find(g => g.id === rawId);
                                    if (confirm(`Delete folder '${groupObj ? groupObj.name : ''}' and all subfolders?`)) {
                                        apiFetch(`/api/bookmarks/groups/${rawId}`, { method: 'DELETE' }).then(() => loadBookmarks());
                                    }
                                }
                            };
                            items.new_bookmark = {
                                separator_before: true,
                                label: "New Bookmark",
                                icon: "fa-solid fa-star",
                                action: function() {
                                    openBookmarkModal(rawId);
                                }
                            };
                            items.new_folder = {
                                label: "New Subfolder",
                                icon: "fa-solid fa-folder-plus",
                                action: function() {
                                    openGroupModal(rawId);
                                }
                            };
                            items.export = {
                                separator_before: true,
                                label: "Export Folder",
                                icon: "fa-solid fa-file-export",
                                action: async function() {
                                    const data = await apiFetch(`/api/bookmarks/groups/${rawId}/export`);
                                    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    const groupObj = bookmarkGroups.find(g => g.id === rawId);
                                    a.download = `kdb_folder_${groupObj ? groupObj.name.toLowerCase().replace(/\s+/g, '_') : rawId}_export.json`;
                                    a.click();
                                    URL.revokeObjectURL(url);
                                }
                            };
                        } else if (isBookmark) {
                            items.edit = {
                                label: "Edit",
                                icon: "fa-solid fa-pen",
                                action: function() {
                                    const bm = bookmarksList.find(b => b.id === rawId);
                                    if (!bm) return;
                                    openBookmarkModal(null, bm);
                                }
                            };
                            items.duplicate = {
                                label: "Duplicate",
                                icon: "fa-solid fa-copy",
                                action: function() {
                                    apiFetch(`/api/bookmarks/${rawId}/duplicate`, { method: 'POST' }).then(() => loadBookmarks());
                                }
                            };
                            items.delete = {
                                label: "Delete",
                                icon: "fa-solid fa-times",
                                action: function() {
                                    const bm = bookmarksList.find(b => b.id === rawId);
                                    if (confirm(`Delete bookmark '${bm ? bm.title : ''}'?`)) {
                                        apiFetch(`/api/bookmarks/${rawId}`, { method: 'DELETE' }).then(() => loadBookmarks());
                                    }
                                }
                            };
                            items.export = {
                                separator_before: true,
                                label: "Export Bookmark",
                                icon: "fa-solid fa-file-export",
                                action: async function() {
                                    const data = await apiFetch(`/api/bookmarks/${rawId}/export`);
                                    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    const bm = bookmarksList.find(b => b.id === rawId);
                                    a.download = `kdb_bookmark_${bm ? bm.title.toLowerCase().replace(/\s+/g, '_') : rawId}_export.json`;
                                    a.click();
                                    URL.revokeObjectURL(url);
                                }
                            };
                        }

                        return items;
                    }
                },
                plugins: ['dnd', 'types', 'contextmenu']
            });

            // Event: Drag & Drop Node Moved
            treeContainer.off('move_node.jstree').on('move_node.jstree', async (e, data) => {
                const movedNode = data.node;
                const parentNode = data.instance.get_node(data.parent);
                
                if (movedNode.data && movedNode.data.isGroup) {
                    const groupId = movedNode.data.rawId;
                    const newParentId = (data.parent === '#' || !parentNode || !parentNode.data || !parentNode.data.isGroup) 
                        ? null 
                        : parentNode.data.rawId;

                    const groupObj = bookmarkGroups.find(g => g.id === groupId);
                    if (groupObj && groupObj.parent_id !== newParentId) {
                        groupObj.parent_id = newParentId;
                        await apiFetch('/api/bookmarks/groups', { method: 'POST', body: JSON.stringify(groupObj) });
                        loadBookmarks();
                    }
                } else if (movedNode.data && movedNode.data.isBookmark) {
                    const bmId = movedNode.data.rawId;
                    const newGroupId = (data.parent === '#' || !parentNode || !parentNode.data || !parentNode.data.isGroup) 
                        ? null 
                        : parentNode.data.rawId;

                    const bm = bookmarksList.find(b => b.id === bmId);
                    if (bm && bm.group_id !== newGroupId) {
                        bm.group_id = newGroupId;
                        await apiFetch('/api/bookmarks', { method: 'POST', body: JSON.stringify(bm) });
                        loadBookmarks();
                    }
                }
            });

            // Event: Bookmark Selected / Clicked
            treeContainer.off('select_node.jstree').on('select_node.jstree', (e, data) => {
                const nodeData = data.node.data;
                if (nodeData && nodeData.isBookmark) {
                    if (nodeData.connId && nodeData.connId !== activeConnectionId) {
                        setActiveConnection(nodeData.connId);
                    }
                    if (nodeData.sql) {
                        editor.setValue(nodeData.sql);
                        runQuery();
                    }
                }
            });
        }

        // Custom Context Menu Trigger for empty space in bookmarks section
        $('#bookmarksSection').off('contextmenu').on('contextmenu', function(e) {
            e.preventDefault();
            // If right-clicked on an actual jsTree node, let jsTree's contextmenu plugin handle it
            if ($(e.target).closest('.jstree-node').length) {
                return;
            }

            // Right click on empty background area
            e.stopPropagation();
            showCustomContextMenu(e.pageX, e.pageY, [
                {
                    label: "New Folder",
                    icon: "fa-solid fa-folder-plus",
                    action: () => openGroupModal()
                },
                {
                    label: "New Bookmark",
                    icon: "fa-solid fa-star",
                    action: () => openBookmarkModal()
                },
                {
                    label: "Import Bookmarks",
                    icon: "fa-solid fa-file-import",
                    action: () => document.getElementById('importFileInput').click()
                }
            ]);
        });

        $('#bookmarksSearchInput').off('input').on('input', function() {
            renderBookmarksTree();
        });
    }

    function showCustomContextMenu(x, y, items) {
        $('.vakata-context').remove();

        const menuUl = $('<ul class="vakata-context jstree-contextmenu jstree-default-contextmenu"></ul>');
        menuUl.css({
            position: 'absolute',
            left: x + 'px',
            top: y + 'px',
            display: 'block',
            zIndex: 10000
        });

        items.forEach(item => {
            const li = $('<li></li>');
            const a = $('<a href="#"><i class="' + item.icon + '"></i> ' + item.label + '</a>');
            a.on('click', (e) => {
                e.preventDefault();
                menuUl.remove();
                item.action();
            });
            li.append(a);
            menuUl.append(li);
        });

        $('body').append(menuUl);

        setTimeout(() => {
            $(document).one('click contextmenu', function() {
                menuUl.remove();
            });
        }, 10);
    }

    // --- Import / Export Bookmarks Handlers ---
    document.getElementById('exportBookmarksBtn').addEventListener('click', async () => {
        const data = await apiFetch('/api/bookmarks/export');
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'kdb_bookmarks_export.json';
        a.click();
        URL.revokeObjectURL(url);
    });

    document.getElementById('importBookmarksBtn').addEventListener('click', () => {
        document.getElementById('importFileInput').click();
    });

    document.getElementById('importFileInput').addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async (evt) => {
            try {
                const data = JSON.parse(evt.target.result);
                const connParam = activeConnectionId ? `?connection_id=${activeConnectionId}` : '';
                await apiFetch(`/api/bookmarks/import${connParam}`, { method: 'POST', body: JSON.stringify(data) });
                alert('Bookmarks imported successfully!');
                loadBookmarks();
            } catch (err) {
                alert(`Import failed: ${err.message}`);
            }
        };
        reader.readAsText(file);
    });

    function openGroupModal(defaultParentId = null, editGroupObj = null) {
        const parentSelect = document.getElementById('groupParentId');
        parentSelect.innerHTML = '<option value="">-- Root (Top-Level Folder) --</option>';

        const currentGroupId = editGroupObj ? editGroupObj.id : null;
        bookmarkGroups.forEach(g => {
            if (currentGroupId && g.id === currentGroupId) return;
            const opt = document.createElement('option');
            opt.value = g.id;
            opt.textContent = g.name;
            parentSelect.appendChild(opt);
        });

        if (editGroupObj) {
            document.getElementById('groupId').value = editGroupObj.id;
            document.getElementById('groupName').value = editGroupObj.name || '';
            document.getElementById('groupColor').value = editGroupObj.color || '#4F46E5';
            parentSelect.value = (editGroupObj.parent_id !== null && editGroupObj.parent_id !== undefined) ? editGroupObj.parent_id : '';
        } else {
            document.getElementById('groupId').value = '';
            document.getElementById('groupName').value = '';
            document.getElementById('groupColor').value = '#4F46E5';
            parentSelect.value = defaultParentId ? defaultParentId : '';

            if (defaultParentId) {
                const pGroup = bookmarkGroups.find(g => g.id === defaultParentId);
                if (pGroup && pGroup.color) {
                    document.getElementById('groupColor').value = pGroup.color;
                }
            }
        }

        openModal('groupModal');
    }

    document.getElementById('newGroupBtn').addEventListener('click', () => openGroupModal());

    document.querySelectorAll('.swatch').forEach(swatch => {
        swatch.addEventListener('click', () => {
            document.getElementById('groupColor').value = swatch.dataset.color;
        });
    });

    document.getElementById('groupParentId').addEventListener('change', (e) => {
        const parentId = e.target.value ? parseInt(e.target.value) : null;
        if (parentId) {
            const parentGroup = bookmarkGroups.find(g => g.id === parentId);
            if (parentGroup && parentGroup.color) {
                document.getElementById('groupColor').value = parentGroup.color;
            }
        } else {
            document.getElementById('groupColor').value = '#4F46E5';
        }
    });

    document.getElementById('groupForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            id: document.getElementById('groupId').value ? parseInt(document.getElementById('groupId').value) : null,
            name: document.getElementById('groupName').value,
            parent_id: document.getElementById('groupParentId').value ? parseInt(document.getElementById('groupParentId').value) : null,
            connection_id: activeConnectionId,
            color: document.getElementById('groupColor').value
        };
        await apiFetch('/api/bookmarks/groups', { method: 'POST', body: JSON.stringify(payload) });
        closeModal('groupModal');
        loadBookmarks();
    });

    function openBookmarkModal(defaultGroupId = null, editBookmarkObj = null) {
        const select = document.getElementById('bmGroupId');
        select.innerHTML = '<option value="">-- No Group (Root) --</option>';
        bookmarkGroups.forEach(g => {
            const opt = document.createElement('option');
            opt.value = g.id;
            opt.textContent = g.name;
            select.appendChild(opt);
        });

        const titleText = document.getElementById('bookmarkModalTitleText');
        const submitBtn = document.getElementById('bookmarkSubmitBtn');

        if (editBookmarkObj) {
            if (titleText) titleText.textContent = 'Edit Bookmark';
            if (submitBtn) submitBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save Changes';

            document.getElementById('bmId').value = editBookmarkObj.id;
            document.getElementById('bmTitle').value = editBookmarkObj.title || '';
            select.value = (editBookmarkObj.group_id !== null && editBookmarkObj.group_id !== undefined) ? editBookmarkObj.group_id : '';
            document.getElementById('bmSqlQuery').value = editBookmarkObj.sql_query || '';
            document.getElementById('bmNotes').value = editBookmarkObj.notes || '';
            document.getElementById('bmTags').value = editBookmarkObj.tags || '';
        } else {
            if (titleText) titleText.textContent = 'Save Bookmark';
            if (submitBtn) submitBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save Bookmark';

            document.getElementById('bmId').value = '';
            document.getElementById('bmTitle').value = '';
            select.value = defaultGroupId ? defaultGroupId : '';
            document.getElementById('bmSqlQuery').value = typeof editor !== 'undefined' ? editor.getValue() : '';
            document.getElementById('bmNotes').value = '';
            document.getElementById('bmTags').value = '';
        }

        openModal('bookmarkModal');
    }

    document.getElementById('saveAsBookmarkBtn').addEventListener('click', () => openBookmarkModal());
    document.getElementById('newBookmarkBtn').addEventListener('click', () => openBookmarkModal());

    document.getElementById('bookmarkForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            id: document.getElementById('bmId').value ? parseInt(document.getElementById('bmId').value) : null,
            group_id: document.getElementById('bmGroupId').value ? parseInt(document.getElementById('bmGroupId').value) : null,
            title: document.getElementById('bmTitle').value,
            connection_id: activeConnectionId,
            sql_query: document.getElementById('bmSqlQuery').value,
            notes: document.getElementById('bmNotes').value,
            tags: document.getElementById('bmTags').value
        };
        await apiFetch('/api/bookmarks', { method: 'POST', body: JSON.stringify(payload) });
        closeModal('bookmarkModal');
        loadBookmarks();
    });

    // --- Query History Modal ---
    document.getElementById('historyBtn').addEventListener('click', async () => {
        const history = await apiFetch('/api/query/history');
        const container = document.getElementById('historyTableContainer');
        
        let html = `
            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <thead>
                    <tr style="text-align: left; border-bottom: 1px solid var(--border-color);">
                        <th style="padding: 8px;">Time</th>
                        <th style="padding: 8px;">DB</th>
                        <th style="padding: 8px;">SQL</th>
                        <th style="padding: 8px;">Duration</th>
                        <th style="padding: 8px;">Rows</th>
                        <th style="padding: 8px;">Status</th>
                    </tr>
                </thead>
                <tbody>
        `;

        history.forEach(h => {
            html += `
                <tr style="border-bottom: 1px solid var(--border-color);">
                    <td style="padding: 8px; color: var(--text-muted);">${h.created_at}</td>
                    <td style="padding: 8px;">${h.connection_name || '-'}</td>
                    <td style="padding: 8px;"><code>${h.sql_query.substring(0, 60)}...</code></td>
                    <td style="padding: 8px;">${h.execution_time_ms} ms</td>
                    <td style="padding: 8px;">${h.row_count}</td>
                    <td style="padding: 8px; color: ${h.status === 'success' ? '#10b981' : '#ef4444'}">${h.status}</td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
        openModal('historyModal');
    });

    // Initial Load: Always start at connection modal
    populateConnForm({});
    loadConnections().then(() => {
        openModal('connectionModal');
    });
    loadBookmarks();
});
