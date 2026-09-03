package com.rui.astockstrategy

import android.app.Application
import com.rui.astockstrategy.v6.BackendClient

class AStockApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        BackendClient.initialize(this)
    }
}
