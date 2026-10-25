package pl.szymon.traininghub

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { HubHome() } }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HubHome() {
    val context = LocalContext.current
    val api = remember { HubApi(context.applicationContext) }
    val scope = rememberCoroutineScope()
    var selected by remember { mutableStateOf("Dzisiaj") }
    var backendUrl by remember { mutableStateOf(api.backendUrl()) }
    var apiKey by remember { mutableStateOf(api.apiKey()) }
    var connected by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("Nie sprawdzono połączenia.") }
    var dashboardText by remember { mutableStateOf("Połącz aplikację z backendem, aby pobrać dane.") }
    var activitiesText by remember { mutableStateOf("Brak pobranej historii.") }
    var statusText by remember { mutableStateOf("Status integracji nie został pobrany.") }
    val tabs = listOf("Dzisiaj", "Historia", "Plan", "Trendy", "Integracje", "Ustawienia")

    fun refresh() {
        scope.launch {
            busy = true
            message = "Łączenie z backendem…"
            try {
                val dashboard = api.getJson("/api/v1/dashboard")
                val activities = api.getJson("/api/v1/activities?limit=20")
                val status = api.getJson("/api/v1/integrations/status")
                val recent = dashboard.optJSONArray("recent_activities")
                val activityItems = activities.optJSONArray("items")
                dashboardText = "Ostatnie aktywności: ${recent?.length() ?: 0}\nDostępne aktywności w historii: ${activities.optInt("total", activityItems?.length() ?: 0)}"
                activitiesText = buildString {
                    if (activityItems == null || activityItems.length() == 0) append("Brak aktywności w backendzie.")
                    else for (i in 0 until activityItems.length()) {
                        val a = activityItems.getJSONObject(i)
                        append("• ${a.optString("name", "Trening")} — ${a.optString("sport_type", "sport")}\n")
                        append("  ${a.optString("started_at", "")}; ${(a.optDouble("distance_m", 0.0) / 1000.0).let { "%.2f".format(it) } } km\n\n")
                    }
                }
                val items = status.optJSONArray("items")
                statusText = buildString {
                    if (items == null || items.length() == 0) append("Backend nie zwrócił statusów źródeł.")
                    else for (i in 0 until items.length()) {
                        val item = items.getJSONObject(i)
                        append("${item.optString("source")}: ${item.optString("status")}\n")
                        item.optString("last_success_at").takeIf { it.isNotBlank() && it != "null" }?.let { append("  Ostatni sukces: $it\n") }
                        item.optString("last_error").takeIf { it.isNotBlank() && it != "null" }?.let { append("  Błąd: $it\n") }
                    }
                }
                connected = true
                message = "Połączenie działa. Dane pobrano z API."
            } catch (e: Exception) {
                connected = false
                message = e.message ?: "Nie udało się połączyć z backendem."
            } finally { busy = false }
        }
    }

    Scaffold(topBar = { TopAppBar(title = { Text("Szymon Training Hub") }) }) { padding ->
        Column(Modifier.padding(padding).fillMaxSize().padding(16.dp)) {
            ScrollableTabRow(selectedTabIndex = tabs.indexOf(selected), edgePadding = 0.dp) {
                tabs.forEach { tab -> Tab(selected == tab, onClick = { selected = tab }, text = { Text(tab) }) }
            }
            Spacer(Modifier.height(12.dp))
            if (selected == "Ustawienia") {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    item { Text("Połączenie z backendem", style = MaterialTheme.typography.titleLarge) }
                    item { OutlinedTextField(value = backendUrl, onValueChange = { backendUrl = it }, label = { Text("Adres backendu") }, placeholder = { Text("https://twoj-serwer") }, modifier = Modifier.fillMaxWidth(), singleLine = true) }
                    item { OutlinedTextField(value = apiKey, onValueChange = { apiKey = it }, label = { Text("Klucz API") }, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth(), singleLine = true) }
                    item { Text("Klucz jest przechowywany lokalnie w zaszyfrowanych preferencjach Androida. Nie zapisuj go w repozytorium GitHub.", style = MaterialTheme.typography.bodySmall) }
                    item { Button(onClick = { runCatching { api.saveSettings(backendUrl, apiKey); message = "Ustawienia zapisane bezpiecznie na tym urządzeniu." }.onFailure { message = it.message ?: "Błędne ustawienia" } }, modifier = Modifier.fillMaxWidth()) { Text("Zapisz ustawienia") } }
                    item { OutlinedButton(onClick = { refresh() }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text(if (busy) "Sprawdzam…" else "Zapisz i sprawdź połączenie") } }
                    item { Text(message) }
                    item { Text("Używaj HTTPS poza zaufaną siecią lokalną. Backend musi być osiągalny z telefonu.", style = MaterialTheme.typography.bodySmall) }
                }
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    item {
                        ElevatedCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp)) {
                                Text(selected, style = MaterialTheme.typography.titleLarge)
                                Spacer(Modifier.height(8.dp))
                                Text(when (selected) {
                                    "Dzisiaj" -> dashboardText
                                    "Historia" -> activitiesText
                                    "Plan" -> "Plan tygodnia i akcje wykonano/pominięto zostaną podłączone w następnym etapie."
                                    "Trendy" -> "Historia metryk: backend ma endpoint /api/v1/metrics/history; wykresy dodamy po potwierdzeniu danych."
                                    else -> statusText
                                })
                            }
                        }
                    }
                    item { OutlinedCard(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp)) {
                        Text("Status połączenia", style = MaterialTheme.typography.titleMedium)
                        Text(message)
                        Text(if (connected) "API: połączone" else "API: niepotwierdzone", style = MaterialTheme.typography.labelMedium)
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = { refresh() }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text(if (busy) "Pobieram…" else "Odśwież dane") }
                        TextButton(onClick = { selected = "Ustawienia" }) { Text("Konfiguruj backend") }
                    } } }
                }
            }
        }
    }
}
