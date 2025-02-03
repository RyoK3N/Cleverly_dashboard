import os
import pandas as pd
import numpy as np
import re
from monday_extract_groups import fetch_items_recursive, fetch_groups
from datetime import datetime

date_pattern = r"\d{4}-\d{2}-\d{2}"

def extract_date(value):
    """
    Extracts date from a string using a regex pattern.
    """
    if pd.isna(value) or value == 'NaT':
        return None
    if isinstance(value, str):
        match = re.search(date_pattern, value)
        return match.group(0) if match else None
    return None

def items_to_dataframe(items):
    """
    Converts a list of items to a pandas DataFrame.
    """
    if not items:
        return pd.DataFrame()
    
    data = []
    column_ids = [column['id'] for column in items[0]['column_values']]
    headers = ['Item ID', 'Item Name'] + column_ids

    for item in items:
        row = {
            'Item ID': item['id'],
            'Item Name': item['name']
        }
        for column in item['column_values']:
            row[column['id']] = column.get('text', '')
        data.append(row)
    
    df = pd.DataFrame(data, columns=headers)
    return df

def fetch_monday_data(api_key):
    """
    Fetches data from Monday.com and returns a dictionary of DataFrames.
    """
    BOARD_ID = "6942829967"
    group_list = [
        "topics",
        "new_group34578__1",
        "new_group27351__1",
        "new_group54376__1",
        "new_group64021__1",
        "new_group65903__1",
        "new_group62617__1"
    ]    
    name_list = [
        "scheduled",
        "unqualified",
        "won",
        "cancelled",
        "noshow",
        "proposal",
        "lost"
    ]
    LIMIT = 500

    try:
        print("\n=== Starting Monday.com Data Fetch ===")
        print(f"Board ID: {BOARD_ID}")
        print(f"API Key (first 10 chars): {api_key[:10]}...")
        
        print("\nFetching groups from Monday.com...")
        groups = fetch_groups(BOARD_ID, api_key)
        print(f"Successfully fetched {len(groups)} groups")
        
        dataframes = {}
        
        for group_id, group_name in zip(group_list, name_list):
            try:
                print(f"\nProcessing group: {group_name} (ID: {group_id})")
                target_group = next((group for group in groups if group['id'] == group_id), None)
                
                if not target_group:
                    print(f"Warning: Group with ID '{group_id}' not found in board {BOARD_ID}.")
                    print("Available groups:", [f"{g['id']}: {g['title']}" for g in groups])
                    continue
                
                print(f"Fetching items for group: {target_group['title']}")
                items = fetch_items_recursive(BOARD_ID, target_group['id'], api_key, LIMIT)
                df_items = items_to_dataframe(items)
                dataframes[group_name] = df_items
                print(f"Successfully fetched {len(df_items)} items for {group_name}")
                
            except Exception as group_error:
                print(f"Error processing group {group_name}: {str(group_error)}")
                import traceback
                print(traceback.format_exc())
                continue

        if not dataframes:
            raise Exception("No data was fetched from any group")

        # Define column renaming mapping
        columns_with_titles = {
            'name': 'Name',
            'auto_number__1': 'Auto number',
            'person': 'Owner',
            'last_updated__1': 'Last updated',
            'link__1': 'Linkedin',
            'phone__1': 'Phone',
            'email__1': 'Email',
            'text7__1': 'Company',
            'date4': 'Sales Call Date',
            'status9__1': 'Follow Up Tracker',
            'notes__1': 'Notes',
            'interested_in__1': 'Interested In',
            'status4__1': 'Plan Type',
            'numbers__1': 'Deal Value',
            'status6__1': 'Email Template #1',
            'dup__of_email_template__1': 'Email Template #2',
            'status__1': 'Deal Status',
            'status2__1': 'Send Panda Doc?',
            'utm_source__1': 'UTM Source',
            'date__1': 'Deal Status Date',
            'utm_campaign__1': 'UTM Campaign',
            'utm_medium__1': 'UTM Medium',
            'utm_content__1': 'UTM Content',
            'link3__1': 'UTM LINK',
            'lead_source8__1': 'Lead Source',
            'color__1': 'Channel FOR FUNNEL METRICS',
            'subitems__1': 'Subitems',
            'date5__1': 'Date Created'
        }

        # Rename columns in each dataframe
        for key in dataframes.keys():
            df = dataframes[key]
            df.rename(columns=columns_with_titles, inplace=True)
            dataframes[key] = df

        print("\nAll data fetched and processed successfully")
        return dataframes
        
    except Exception as e:
        print(f"\nError in fetch_monday_data: {str(e)}")
        import traceback
        print("Traceback:")
        print(traceback.format_exc())
        raise

def filter_date(df, date_column, start_date, end_date):
    """Filter DataFrame based on date range"""
    try:
        # Convert dates to datetime, handling both date-only and datetime formats
        df_dates = pd.to_datetime(df[date_column], format='mixed')
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        
        # Create mask for date range
        mask = (df_dates >= start) & (df_dates <= end)
        return df[mask]
    except Exception as e:
        print(f"Error in filter_date: {e}")
        return df  # Return original DataFrame if filtering fails

def process_sales_data(dataframes, start_date, end_date, date_column='Date Created', owner_filter=None):
    """Process sales data and calculate metrics"""
    try:
        # Extract individual dataframes
        scheduled = dataframes.get('scheduled', pd.DataFrame())
        unqualified = dataframes.get('unqualified', pd.DataFrame())
        won = dataframes.get('won', pd.DataFrame())
        cancelled = dataframes.get('cancelled', pd.DataFrame())
        noshow = dataframes.get('noshow', pd.DataFrame())
        proposal = dataframes.get('proposal', pd.DataFrame())
        lost = dataframes.get('lost', pd.DataFrame())

        # Combine all deals for total metrics
        all_deal = pd.concat([scheduled, unqualified, won, cancelled, noshow, proposal, lost], ignore_index=True)
        
        # Create opportunity dataframes
        op_unqualified = unqualified.copy()
        op_proposal = proposal.copy()
        op_won = won.copy()
        op_lost = lost.copy()

        # Initialize DataFrame with owners
        df = pd.DataFrame()
        df['Owner'] = pd.Series(all_deal['Owner'].dropna()).unique()

        if owner_filter:
            df = df[df['Owner'].isin(owner_filter)]

        # Calculate metrics
        subset = all_deal
        
        # New Calls Booked
        new_calls_booked = filter_date(subset, date_column, start_date, end_date).groupby('Owner').size()
        df['New Calls Booked'] = df['Owner'].map(new_calls_booked).fillna(0).astype(int)
        total_ncb = df['New Calls Booked'].sum()

        # Sales Call Taken
        df_subset = pd.concat([op_unqualified, op_proposal, op_won, op_lost], ignore_index=True)
        sales_calls_taken = filter_date(df_subset, date_column, start_date, end_date).groupby('Owner').size()
        df['Sales Call Taken'] = df['Owner'].map(sales_calls_taken).fillna(0).astype(int)
        total_sct = df['Sales Call Taken'].sum()

        # Show Rate
        show_rate = sales_calls_taken / df.set_index('Owner')['New Calls Booked']
        show_rate = show_rate.replace([np.inf, -np.inf], 0).fillna(0)
        df['Show Rate %'] = df['Owner'].map(show_rate) * 100
        total_show = (total_sct / total_ncb) * 100 if total_ncb != 0 else 0

        # Unqualified Rate
        df_subset = op_unqualified.copy()
        uq = filter_date(df_subset, date_column, start_date, end_date).groupby('Owner').size()
        uq_rate = uq / df.set_index('Owner')['New Calls Booked']
        uq_rate = uq_rate.replace([np.inf, -np.inf], 0).fillna(0)
        df['Unqualified Rate %'] = df['Owner'].map(uq_rate) * 100
        total_uq_rate = (filter_date(df_subset, date_column, start_date, end_date).shape[0] / total_ncb) * 100 if total_ncb != 0 else 0

        # Cancellation Rate
        df_subset = cancelled.copy()
        canc = filter_date(df_subset, date_column, start_date, end_date).groupby('Owner').size()
        canc_rate = canc / df.set_index('Owner')['New Calls Booked']
        canc_rate = canc_rate.replace([np.inf, -np.inf], 0).fillna(0)
        df['Cancellation Rate %'] = df['Owner'].map(canc_rate) * 100
        total_canc_rate = (filter_date(df_subset, date_column, start_date, end_date).shape[0] / total_ncb) * 100 if total_ncb != 0 else 0

        # Proposal Rate
        df_subset = proposal.copy()
        prop = filter_date(df_subset, date_column, start_date, end_date).groupby('Owner').size()
        won_r = filter_date(op_won.copy(), date_column, start_date, end_date).groupby('Owner').size()
        prop_rate = (prop + won_r) / df.set_index('Owner')['New Calls Booked']
        prop_rate = prop_rate.replace([np.inf, -np.inf], 0).fillna(0)
        df['Proposal Rate %'] = df['Owner'].map(prop_rate) * 100
        total_prop_rate = ((filter_date(op_proposal.copy(), date_column, start_date, end_date).shape[0] + 
                           filter_date(op_won.copy(), date_column, start_date, end_date).shape[0]) / total_ncb) * 100 if total_ncb != 0 else 0

        # Close Rate
        df_subset = op_won.copy()
        close = filter_date(df_subset, date_column, start_date, end_date).groupby('Owner').size()
        close_rate = close / df.set_index('Owner')['New Calls Booked']
        close_rate = close_rate.replace([np.inf, -np.inf], 0).fillna(0)
        df['Close Rate %'] = df['Owner'].map(close_rate) * 100
        total_close = filter_date(df_subset, date_column, start_date, end_date).shape[0]
        total_close_rate = (total_close / total_ncb) * 100 if total_ncb != 0 else 0

        # Close Rate (Show)
        close_rate_show = close / df.set_index('Owner')['Sales Call Taken']
        close_rate_show = close_rate_show.replace([np.inf, -np.inf], 0).fillna(0)
        df['Close Rate(Show) %'] = df['Owner'].map(close_rate_show) * 100
        total_close_rate_show = (total_close / total_sct) * 100 if total_sct != 0 else 0

        # Close Rate (MQL)
        df_subset2 = proposal.copy()
        prop_show_mql = filter_date(df_subset2, date_column, start_date, end_date).groupby('Owner').size()
        close_show_rate_mql = close / prop_show_mql
        close_show_rate_mql = close_show_rate_mql.replace([np.inf, -np.inf], 0).fillna(0)
        df['Close Rate(MQL) %'] = df['Owner'].map(close_show_rate_mql) * 100
        total_proposal_mql = filter_date(df_subset2, date_column, start_date, end_date).shape[0] + filter_date(op_won.copy(), date_column, start_date, end_date).shape[0]
        total_close_rate_mql = (total_close / total_proposal_mql) * 100 if total_proposal_mql != 0 else 0

        # Closed Revenue
        df_subset = op_won.copy()
        close_rev = filter_date(df_subset, date_column, start_date, end_date)
        close_rev = close_rev.copy()
        close_rev['Deal Value'] = pd.to_numeric(close_rev['Deal Value'], errors='coerce').fillna(0)
        owner_sum = close_rev.groupby('Owner')['Deal Value'].sum()
        df['Closed Revenue $'] = df['Owner'].map(owner_sum).fillna(0)
        total_cr = df['Closed Revenue $'].sum()

        # Revenue per Call
        rev_per_call = owner_sum / df.set_index('Owner')['New Calls Booked']
        rev_per_call = rev_per_call.replace([np.inf, -np.inf], 0).fillna(0)
        df['Revenue Per Call $'] = df['Owner'].map(rev_per_call).fillna(0)
        total_rev_per_call = total_cr / total_ncb if total_ncb != 0 else 0

        # Revenue per Showed Up
        rev_per_showed_up = owner_sum / df.set_index('Owner')['Sales Call Taken']
        rev_per_showed_up = rev_per_showed_up.replace([np.inf, -np.inf], 0).fillna(0)
        df['Revenue Per Showed Up $'] = df['Owner'].map(rev_per_showed_up).fillna(0)
        total_rev_per_showedup = total_cr / total_sct if total_sct != 0 else 0

        # Revenue Per Proposal
        rev_per_proposal = owner_sum / prop
        rev_per_proposal = rev_per_proposal.replace([np.inf, -np.inf], 0).fillna(0)
        df['Revenue Per Proposal $'] = df['Owner'].map(rev_per_proposal).fillna(0)
        total_rev_per_proposal = total_cr / total_proposal_mql if total_proposal_mql != 0 else 0

        # Pipeline Revenue
        df_subset = proposal.copy()
        pipeline_rev = filter_date(df_subset, date_column, start_date, end_date)
        pipeline_rev = pipeline_rev.copy()
        pipeline_rev['Deal Value'] = pd.to_numeric(pipeline_rev['Deal Value'], errors='coerce').fillna(0)
        owner_sum_prop = pipeline_rev.groupby('Owner')['Deal Value'].sum()
        df['Pipeline Revenue $'] = df['Owner'].map(owner_sum_prop).fillna(0)
        total_pipeline_rev = df['Pipeline Revenue $'].sum()

        # Add totals row
        totals = {
            'Owner': 'Total',
            'New Calls Booked': total_ncb,
            'Sales Call Taken': total_sct,
            'Show Rate %': total_show,
            'Unqualified Rate %': total_uq_rate,
            'Cancellation Rate %': total_canc_rate,
            'Proposal Rate %': total_prop_rate,
            'Close Rate %': total_close_rate,
            'Close Rate(Show) %': total_close_rate_show,
            'Close Rate(MQL) %': total_close_rate_mql,
            'Closed Revenue $': total_cr,
            'Revenue Per Call $': total_rev_per_call,
            'Revenue Per Showed Up $': total_rev_per_showedup,
            'Revenue Per Proposal $': total_rev_per_proposal,
            'Pipeline Revenue $': total_pipeline_rev
        }
        
        df = pd.concat([df, pd.DataFrame([totals])], ignore_index=True)
        
        return df.to_dict('records')
    except Exception as e:
        print(f"Error in process_sales_data: {e}")
        raise

def get_performance_metrics(dataframes, start_date, end_date):
    """Calculate performance metrics for charts"""
    try:
        processed_data = process_sales_data(dataframes, start_date, end_date)
        metrics = {
            'closed_revenue': [],
            'close_rate': [],
            'new_calls': [],
            'sales_calls_taken': []
        }
        
        for record in processed_data:
            if record['Owner'] != 'Total':
                metrics['closed_revenue'].append({
                    'owner': record['Owner'],
                    'value': record.get('Closed Revenue $', 0)
                })
                metrics['close_rate'].append({
                    'owner': record['Owner'],
                    'value': record.get('Close Rate %', 0)
                })
                metrics['new_calls'].append({
                    'owner': record['Owner'],
                    'value': record.get('New Calls Booked', 0)
                })
                metrics['sales_calls_taken'].append({
                    'owner': record['Owner'],
                    'value': record.get('Sales Call Taken', 0)
                })
        
        return metrics
    except Exception as e:
        print(f"Error in get_performance_metrics: {e}")
        raise 