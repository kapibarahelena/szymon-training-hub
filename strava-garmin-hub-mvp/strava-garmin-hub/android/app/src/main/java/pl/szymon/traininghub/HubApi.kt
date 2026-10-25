package pl.szymon.traininghub

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class HubApi(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context,
        "hub_secure_settings",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    fun backendUrl(): String = prefs.getString("backend_url", "https://your-hub.example") ?: "https://your-hub.example"
    fun apiKey(): String = prefs.getString("api_key", "") ?: ""

    fun saveSettings(url: String, key: String) {
        val normalized = url.trim().trimEnd('/')
        require(normalized.startsWith("https://") || normalized.startsWith("http://")) { "Adres musi zaczynać się od http:// lub https://" }
        require(key.isNotBlank()) { "Wpisz klucz API" }
        prefs.edit().putString("backend_url", normalized).putString("api_key", key.trim()).apply()
    }

    suspend fun getJson(path: String): JSONObject = withContext(Dispatchers.IO) {
        val base = backendUrl().trimEnd('/')
        val key = apiKey()
        require(key.isNotBlank()) { "Najpierw zapisz klucz API w ustawieniach." }
        val connection = (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 8000
            readTimeout = 12000
            setRequestProperty("X-Hub-API-Key", key)
            setRequestProperty("Accept", "application/json")
        }
        try {
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val body = stream.bufferedReader().use { it.readText() }
            if (code !in 200..299) {
                val detail = runCatching { JSONObject(body).optString("detail") }.getOrDefault(body)
                throw IllegalStateException("API HTTP $code: $detail")
            }
            JSONObject(body)
        } finally { connection.disconnect() }
    }
}
