package net.munea.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * 打開「沐寧的通知設定」系統頁（2026-11-20，補助案 B2 提醒流程）。
 *
 * 使用者拒絕通知權限後，App 會說「可以到手機設定打開」；這支讓那個按鈕直接跳到
 * 沐寧自己的通知設定，不用長輩自己在系統設定裡找。iOS 的同一件事在 NotifyPlugin.openSettings。
 * 官方 local-notifications 外掛沒有這個功能，所以 App 自己帶一支最小的。
 */
@CapacitorPlugin(name = "MuneaNotificationSettings")
public class NotificationSettingsPlugin extends Plugin {

    @PluginMethod
    public void open(PluginCall call) {
        String packageName = getContext().getPackageName();
        Intent intent;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            intent = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS);
            intent.putExtra(Settings.EXTRA_APP_PACKAGE, packageName);
        } else {
            intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + packageName));
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        JSObject result = new JSObject();
        try {
            getActivity().startActivity(intent);
            result.put("opened", true);
        } catch (Exception e) {
            result.put("opened", false);
        }
        call.resolve(result);
    }
}
