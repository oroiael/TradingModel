/* Copyright (C) 2025 Interactive Brokers LLC. All rights reserved. This code is subject to the terms
 * and conditions of the IB API Non-Commercial License or the IB API Commercial License, as applicable. */

using System.Collections.Generic;

namespace IBApi
{
    public static class Constants
    {
        public const int ClientVersion = 66; //API v. 9.71
        public const byte EOL = 0;
        public const string BagSecType = "BAG";
        public const string INFINITY_STR = "Infinity";

        public const int FaGroups = 1;
        public const int FaAliases = 3;
        public const int MinVersion = 100;
        public const int MaxVersion = MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA;
        public const int MaxMsgSize = 0x00FFFFFF;

        public const int PROTOBUF_MSG_ID = 200;
        public static readonly Dictionary<OutgoingMessages, int> PROTOBUF_MSG_IDS = new Dictionary<OutgoingMessages, int>()
        {
            { OutgoingMessages.RequestExecutions, MinServerVer.MIN_SERVER_VER_PROTOBUF },
            { OutgoingMessages.PlaceOrder, MinServerVer.MIN_SERVER_VER_PROTOBUF_PLACE_ORDER },
            { OutgoingMessages.CancelOrder, MinServerVer.MIN_SERVER_VER_PROTOBUF_PLACE_ORDER },
            { OutgoingMessages.RequestGlobalCancel, MinServerVer.MIN_SERVER_VER_PROTOBUF_PLACE_ORDER },
            { OutgoingMessages.RequestAllOpenOrders, MinServerVer.MIN_SERVER_VER_PROTOBUF_COMPLETED_ORDER },
            { OutgoingMessages.RequestAutoOpenOrders, MinServerVer.MIN_SERVER_VER_PROTOBUF_COMPLETED_ORDER },
            { OutgoingMessages.RequestOpenOrders, MinServerVer.MIN_SERVER_VER_PROTOBUF_COMPLETED_ORDER },
            { OutgoingMessages.ReqCompletedOrders, MinServerVer.MIN_SERVER_VER_PROTOBUF_COMPLETED_ORDER },
            { OutgoingMessages.RequestContractData, MinServerVer.MIN_SERVER_VER_PROTOBUF_CONTRACT_DATA },
            { OutgoingMessages.RequestMarketData, MinServerVer.MIN_SERVER_VER_PROTOBUF_MARKET_DATA },
            { OutgoingMessages.CancelMarketData, MinServerVer.MIN_SERVER_VER_PROTOBUF_MARKET_DATA },
            { OutgoingMessages.RequestMarketDepth, MinServerVer.MIN_SERVER_VER_PROTOBUF_MARKET_DATA },
            { OutgoingMessages.CancelMarketDepth, MinServerVer.MIN_SERVER_VER_PROTOBUF_MARKET_DATA },
            { OutgoingMessages.RequestMarketDataType, MinServerVer.MIN_SERVER_VER_PROTOBUF_MARKET_DATA },
            { OutgoingMessages.RequestAccountData, MinServerVer.MIN_SERVER_VER_PROTOBUF_ACCOUNTS_POSITIONS },
            { OutgoingMessages.RequestManagedAccounts, MinServerVer.MIN_SERVER_VER_PROTOBUF_ACCOUNTS_POSITIONS },
            { OutgoingMessages.RequestPositions, MinServerVer.MIN_SERVER_VER_PROTOBUF_ACCOUNTS_POSITIONS },
            { OutgoingMessages.CancelPositions, MinServerVer.MIN_SERVER_VER_PROTOBUF_ACCOUNTS_POSITIONS },
            { OutgoingMessages.RequestAccountSummary, MinServerVer.MIN_SERVER_VER_PROTOBUF_ACCOUNTS_POSITIONS },
            { OutgoingMessages.CancelAccountSummary, MinServerVer.MIN_SERVER_VER_PROTOBUF_ACCOUNTS_POSITIONS },
            { OutgoingMessages.RequestPositionsMulti, MinServerVer.MIN_SERVER_VER_PROTOBUF_ACCOUNTS_POSITIONS },
            { OutgoingMessages.CancelPositionsMulti, MinServerVer.MIN_SERVER_VER_PROTOBUF_ACCOUNTS_POSITIONS },
            { OutgoingMessages.RequestAccountUpdatesMulti, MinServerVer.MIN_SERVER_VER_PROTOBUF_ACCOUNTS_POSITIONS },
            { OutgoingMessages.CancelAccountUpdatesMulti, MinServerVer.MIN_SERVER_VER_PROTOBUF_ACCOUNTS_POSITIONS },
            { OutgoingMessages.RequestHistoricalData, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA },
            { OutgoingMessages.CancelHistoricalData, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA },
            { OutgoingMessages.RequestRealTimeBars, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA },
            { OutgoingMessages.CancelRealTimeBars, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA },
            { OutgoingMessages.RequestHeadTimestamp, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA },
            { OutgoingMessages.CancelHeadTimestamp, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA },
            { OutgoingMessages.RequestHistogramData, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA },
            { OutgoingMessages.CancelHistogramData, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA },
            { OutgoingMessages.ReqHistoricalTicks, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA },
            { OutgoingMessages.ReqTickByTickData, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA },
            { OutgoingMessages.CancelTickByTickData, MinServerVer.MIN_SERVER_VER_PROTOBUF_HISTORICAL_DATA }
        };
    }
}
