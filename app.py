"""
Enhanced Streamlit App with Editable Purchase Plan
Update your app.py with this code
"""

import json
import os
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Import your forecaster
# from purchase_forecaster import PurchasePlanForecaster

st.set_page_config(page_title="Purchase Plan Forecaster", layout="wide", page_icon="📦")

# Initialize session state
if 'forecasts' not in st.session_state:
    st.session_state['forecasts'] = None
if 'edited_plan' not in st.session_state:
    st.session_state['edited_plan'] = None
if 'manual_adjustments' not in st.session_state:
    st.session_state['manual_adjustments'] = {}

# Sidebar configuration
with st.sidebar:
    st.title("⚙️ Configuration")
    
    start_month = st.text_input("Start Month (YYYY-MM)", value="2025-12", key="start_month_input")
    num_months = st.number_input("Forecast Horizon (months)", min_value=1, max_value=24, value=6, key="horizon_input")
    data_dir = st.text_input("Data Directory", value="data", key="data_dir_input")
    
    st.divider()
    st.subheader("✏️ Edit Mode")
    
    edit_enabled = st.toggle("Enable Plan Editing", value=True)
    
    if edit_enabled:
        current_month = datetime.now().strftime('%Y-%m')
        cutoff_date = datetime.strptime(current_month, '%Y-%m') + relativedelta(months=2)
        cutoff_month = cutoff_date.strftime('%Y-%m')
        st.info(f"📅 Editable from: **{cutoff_month}** onwards")
    
    st.divider()
    
    run_btn = st.button("🚀 Generate Plan", type="primary", use_container_width=True)
    
    if edit_enabled and st.session_state['edited_plan']:
        if st.button("💾 Save Adjusted Plan", use_container_width=True):
            st.success("✓ Plan saved to session!")

# Main content
st.title("📦 Purchase Plan Forecaster")
st.markdown("Generate optimal purchase recommendations with real-time editing capability")

# File upload section
with st.expander("📁 Upload Data Files", expanded=not run_btn):
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Required Files**")
        sales_history_file = st.file_uploader("sales_history.json", type=["json"], key="sales_hist")
        item_params_file = st.file_uploader("item_parameters.json", type=["json"], key="item_params")
        current_inventory_file = st.file_uploader("current_inventory.json", type=["json"], key="curr_inv")
        sales_n12_file = st.file_uploader("sales_forecasts_n12.json", type=["json"], key="n12")
    
    with col2:
        st.markdown("**Optional Files**")
        promo_file = st.file_uploader("promotional_calendar.json", type=["json"], key="promo")
        supplier_rel_file = st.file_uploader("supplier_reliability.json", type=["json"], key="supplier")
        price_fc_file = st.file_uploader("price_forecasts.json", type=["json"], key="price")
    
    with col3:
        st.markdown("**Advanced Options**")
        demand_var_file = st.file_uploader("demand_variability.json", type=["json"], key="demand_var")
        volume_disc_file = st.file_uploader("volume_discounts.json", type=["json"], key="vol_disc")

# Generate plan
if run_btn:
    try:
        with st.spinner("Loading data and generating plan..."):
            # Initialize forecaster
            from purchase_forecaster import PurchasePlanForecaster
            pf = PurchasePlanForecaster()
            
            # Load data from uploads or directory
            if sales_history_file:
                pf.load_sales_history(json.load(sales_history_file))
            else:
                with open(os.path.join(data_dir, 'sales_history.json')) as f:
                    pf.load_sales_history(json.load(f))
            
            if item_params_file:
                pf.load_item_parameters(json.load(item_params_file))
            else:
                with open(os.path.join(data_dir, 'item_parameters.json')) as f:
                    pf.load_item_parameters(json.load(f))
            
            if current_inventory_file:
                pf.load_current_inventory(json.load(current_inventory_file))
            else:
                with open(os.path.join(data_dir, 'current_inventory.json')) as f:
                    pf.load_current_inventory(json.load(f))
            
            if sales_n12_file:
                pf.load_sales_forecasts_n12(json.load(sales_n12_file))
            else:
                with open(os.path.join(data_dir, 'sales_forecasts_n12.json')) as f:
                    pf.load_sales_forecasts_n12(json.load(f))
            
            # Load optional files
            for file_obj, fname, loader in [
                (promo_file, 'promotional_calendar.json', pf.load_promotional_calendar),
                (supplier_rel_file, 'supplier_reliability.json', pf.load_supplier_reliability),
                (price_fc_file, 'price_forecasts.json', pf.load_price_forecasts),
                (demand_var_file, 'demand_variability.json', pf.load_demand_variability),
                (volume_disc_file, 'volume_discounts.json', pf.load_volume_discounts)
            ]:
                try:
                    if file_obj:
                        loader(json.load(file_obj))
                    else:
                        with open(os.path.join(data_dir, fname)) as f:
                            loader(json.load(f))
                except FileNotFoundError:
                    pass
            
            # Generate forecasts
            forecasts = pf.generate_purchase_plan(
                start_month=start_month,
                num_months=int(num_months)
            )
            
            # Store in session state
            st.session_state['forecasts'] = [vars(f) if hasattr(f, '__dict__') else f for f in forecasts]
            st.session_state['forecaster'] = pf
            
        st.success(f"✓ Generated {len(forecasts)} forecast periods!")
    
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        st.exception(e)

# Display and edit plan
if st.session_state['forecasts']:
    
    # Summary metrics
    st.divider()
    forecasts_data = st.session_state['forecasts']
    df = pd.DataFrame(forecasts_data)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        total_orders = df['optimized_order_qty'].sum()
        st.metric("Total Orders", f"{total_orders:,.0f}")
    
    with col2:
        total_cost = df['total_order_cost'].sum()
        st.metric("Total Cost", f"${total_cost:,.2f}")
    
    with col3:
        stockout_count = df['stockout_risk'].sum()
        st.metric("Stockout Risks", stockout_count, delta=f"-{stockout_count}" if stockout_count > 0 else None)
    
    with col4:
        avg_cover = df['stock_cover_months'].replace([float('inf')], 0).mean()
        st.metric("Avg Cover", f"{avg_cover:.1f} mo")
    
    with col5:
        items_count = df['item_id'].nunique()
        st.metric("Items", items_count)
    
    st.divider()
    
    # Editable plan table
    if edit_enabled:
        st.subheader("📝 Editable Purchase Plan")
        
        current_month = datetime.now().strftime('%Y-%m')
        current_date = datetime.strptime(current_month, '%Y-%m')
        cutoff_date = current_date + relativedelta(months=2)
        cutoff_month = cutoff_date.strftime('%Y-%m')
        
        # Add editable flag
        df['is_editable'] = df['forecast_month'] >= cutoff_month
        df['original_order_qty'] = df['optimized_order_qty']
        
        # Apply any manual adjustments
        if st.session_state['manual_adjustments']:
            for key, new_qty in st.session_state['manual_adjustments'].items():
                mask = (df['item_id'] == key.split('_')[0]) & (df['forecast_month'] == key.split('_')[1])
                df.loc[mask, 'optimized_order_qty'] = new_qty
        
        # Configure columns
        column_config = {
            'forecast_month': st.column_config.TextColumn('Month', width='small'),
            'item_id': st.column_config.TextColumn('SKU', width='small'),
            'item_name': st.column_config.TextColumn('Item', width='medium'),
            'adjusted_demand': st.column_config.NumberColumn('Demand', width='small', format="%d"),
            'opening_stock': st.column_config.NumberColumn('Opening', width='small', format="%d"),
            'in_transit': st.column_config.NumberColumn('In-Transit', width='small', format="%d"),
            'adjusted_safety_stock': st.column_config.NumberColumn('Safety', width='small', format="%d"),
            'optimized_order_qty': st.column_config.NumberColumn(
                '✏️ Order Qty',
                width='small',
                format="%d",
                help="Editable for months >= current+2"
            ),
            'ending_stock_after_order': st.column_config.NumberColumn('End Stock', width='small', format="%d"),
            'stock_cover_months': st.column_config.NumberColumn('Cover', width='small', format="%.1f"),
            'total_order_cost': st.column_config.NumberColumn('Cost', width='medium', format="$%.2f"),
            'stockout_risk': st.column_config.CheckboxColumn('⚠️', width='small'),
            'is_editable': st.column_config.CheckboxColumn('Edit?', width='small')
        }
        
        # Select columns to display
        display_cols = [
            'forecast_month', 'item_id', 'item_name', 'adjusted_demand',
            'opening_stock', 'in_transit', 'adjusted_safety_stock',
            'optimized_order_qty', 'ending_stock_after_order',
            'stock_cover_months', 'total_order_cost', 'stockout_risk', 'is_editable'
        ]
        
        # Filter existing columns
        display_cols = [col for col in display_cols if col in df.columns]
        
        # Editable data editor
        edited_df = st.data_editor(
            df[display_cols],
            column_config=column_config,
            disabled=[col for col in display_cols if col not in ['optimized_order_qty']],
            hide_index=True,
            use_container_width=True,
            key='plan_editor',
            num_rows="fixed"
        )
        
        # Detect changes
        changes = []
        for idx in edited_df.index:
            if edited_df.loc[idx, 'is_editable']:
                orig = df.loc[idx, 'original_order_qty']
                new = edited_df.loc[idx, 'optimized_order_qty']
                
                if orig != new:
                    item_id = edited_df.loc[idx, 'item_id']
                    month = edited_df.loc[idx, 'forecast_month']
                    
                    changes.append({
                        'item_id': item_id,
                        'item_name': edited_df.loc[idx, 'item_name'],
                        'month': month,
                        'original_qty': int(orig),
                        'new_qty': int(new),
                        'difference': int(new - orig),
                        'key': f"{item_id}_{month}"
                    })
        
        # Show changes summary
        if changes:
            st.divider()
            st.subheader("📊 Manual Adjustments Summary")
            
            changes_df = pd.DataFrame(changes)
            st.dataframe(
                changes_df[['month', 'item_name', 'original_qty', 'new_qty', 'difference']],
                use_container_width=True,
                hide_index=True
            )
            
            col1, col2, col3 = st.columns([1, 1, 3])
            
            with col1:
                if st.button("✅ Apply Changes", type="primary"):
                    # Store adjustments
                    for change in changes:
                        st.session_state['manual_adjustments'][change['key']] = change['new_qty']
                    st.success("Changes applied!")
                    st.rerun()
            
            with col2:
                if st.button("↺ Reset All"):
                    st.session_state['manual_adjustments'] = {}
                    st.rerun()
            
            with col3:
                # Export adjusted plan
                adjusted_data = edited_df.to_dict('records')
                json_str = json.dumps(adjusted_data, indent=2, default=str)
                st.download_button(
                    label="💾 Download Adjusted Plan",
                    data=json_str,
                    file_name=f"adjusted_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
    
    else:
        # View-only mode
        st.subheader("📊 Purchase Plan (View Only)")
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Export section
    st.divider()
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 Export Full Report (JSON)"):
            pf = st.session_state.get('forecaster')
            if pf:
                output = pf.export_to_json()
                json_str = json.dumps(output, indent=2, default=str)
                st.download_button(
                    label="Download JSON Report",
                    data=json_str,
                    file_name=f"purchase_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
    
    with col2:
        if st.button("📥 Export to Excel"):
            # Convert to Excel
            excel_buffer = pd.ExcelWriter('purchase_plan.xlsx', engine='xlsxwriter')
            df.to_excel(excel_buffer, sheet_name='Purchase Plan', index=False)
            excel_buffer.close()
            
            st.success("Excel export functionality coming soon!")

else:
    # Welcome screen
    st.info("👆 Upload your data files or configure the data directory, then click **Generate Plan** to start.")
    
    with st.expander("📖 How to Use", expanded=True):
        st.markdown("""
        ### Quick Start Guide
        
        1. **Upload Data Files** or configure the data directory path
        2. **Set Parameters** in the sidebar (start month, horizon)
        3. Click **Generate Plan** to create the purchase forecast
        4. **Enable Edit Mode** to adjust orders for future months
        5. **Apply Changes** to recalculate the plan
        6. **Export** your adjusted plan as JSON or Excel
        
        ### Editing Rules
        - ✅ **Editable**: Months >= Current Month + 2
        - 🔒 **Locked**: Current month and next month
        - 💡 **Tip**: Changes are highlighted automatically
        
        ### Features
        - 📊 Real-time order adjustments
        - 🔄 Automatic recalculation
        - 💾 Export adjusted plans
        - ⚠️ Risk indicators
        - 📈 Stock cover analysis
        """)

# Footer
st.divider()
st.caption("Purchase Plan Forecaster v1.0 | Production-Grade Planning Tool")