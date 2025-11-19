module width_demo (
    input  logic              clk,
    input  logic [7:0]        data_in,
    output logic              flag,
    output logic [15:0]       wide_bus
);
    logic [3:0] nibble;
    logic [2:0] narrow;
    logic [7:0] line_mem [0:3];

    assign nibble = data_in[7:4];
    assign narrow = data_in[2:0];
    assign wide_bus = {data_in, data_in};
    assign flag = nibble[3];

endmodule
