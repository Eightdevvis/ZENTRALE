package de.zentrale.zen_mobile

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, UPDATE_CHANNEL)
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "info" -> result.success(info())
                        "canInstall" -> result.success(canInstall())
                        "openInstallSettings" -> {
                            openInstallSettings()
                            result.success(null)
                        }
                        "isMetered" -> result.success(isMetered())
                        "install" -> {
                            val path = call.argument<String>("path")
                            if (path == null) {
                                result.error("bad_args", "path missing", null)
                            } else {
                                install(File(path))
                                result.success(null)
                            }
                        }
                        else -> result.notImplemented()
                    }
                } catch (e: Exception) {
                    result.error("update_failed", e.message, null)
                }
            }
    }

    private fun updateDir(): File = File(cacheDir, "updates").apply { mkdirs() }

    @Suppress("DEPRECATION")
    private fun packageInfo(): PackageInfo =
        if (Build.VERSION.SDK_INT >= 33) {
            packageManager.getPackageInfo(packageName, PackageManager.PackageInfoFlags.of(0))
        } else {
            packageManager.getPackageInfo(packageName, 0)
        }

    @Suppress("DEPRECATION")
    private fun installer(): String? =
        try {
            if (Build.VERSION.SDK_INT >= 30) {
                packageManager.getInstallSourceInfo(packageName).installingPackageName
            } else {
                packageManager.getInstallerPackageName(packageName)
            }
        } catch (e: Exception) {
            null
        }

    @Suppress("DEPRECATION")
    private fun info(): Map<String, Any?> {
        val p = packageInfo()
        val code = if (Build.VERSION.SDK_INT >= 28) p.longVersionCode else p.versionCode.toLong()
        val from = installer()
        // Self-update only in our own build and never in a copy Google Play installed.
        val selfUpdate = BuildConfig.SELF_UPDATE && from != PLAY_STORE
        return mapOf(
            "versionName" to p.versionName,
            "versionCode" to code,
            "selfUpdate" to selfUpdate,
            "installer" to from,
            "updateDir" to updateDir().absolutePath,
        )
    }

    private fun canInstall(): Boolean =
        Build.VERSION.SDK_INT < 26 || packageManager.canRequestPackageInstalls()

    private fun openInstallSettings() {
        if (Build.VERSION.SDK_INT < 26) return
        val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName"))
        try {
            startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS))
        }
    }

    private fun isMetered(): Boolean {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        return cm.isActiveNetworkMetered
    }

    private fun install(apk: File) {
        // Only files from our own update folder (the Dart side verified the SHA-256).
        val dir = updateDir().canonicalFile
        val file = apk.canonicalFile
        require(file.parentFile == dir && file.isFile) { "not an update file" }
        val uri = FileProvider.getUriForFile(this, "$packageName.updates", file)
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(intent)
    }

    companion object {
        const val UPDATE_CHANNEL = "de.zentrale.zen_mobile/update"
        const val PLAY_STORE = "com.android.vending"
    }
}
