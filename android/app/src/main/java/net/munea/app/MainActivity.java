package net.munea.app;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // App 自帶的原生小外掛要在橋建立前登記（2026-11-08 通話中螢幕不睡）
        registerPlugin(KeepAwakePlugin.class);
        // 通知被關掉時，「到手機設定打開」要能直接跳到沐寧的通知設定頁（2026-11-20 提醒流程）
        registerPlugin(NotificationSettingsPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
