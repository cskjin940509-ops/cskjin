package com.rui.astockstrategy.v4

import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier

/** Centers standalone composables horizontally when no ColumnScope align modifier is available. */
fun Modifier.align(alignment: Alignment.Horizontal): Modifier = this.wrapContentWidth(alignment)
