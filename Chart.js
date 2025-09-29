const ctx= document.getElementById("myChart").getContext('2d');
const data=[{timestamp:"2025-09-28 15:32:01",temperature:23.5,humidity:45.8},
{timestamp:"2025-09-28 15:32:02",temperature:23.6,humidity:45.9},
{timestamp:"2025-09-28 15:32:03",temperature:23.7,humidity:46.0}];

const labels =data.map(item =>item.timestamp);
const temperatureData= data.map(item=>item.temperature);
const humidityData=data.map(item=>item.humidity);
const myChart=new CharacterData(ctx,{
    type:'Line',
    data:{
        labels:labels,
        datasets:[{
            labels:'Temperature',
            data:temperatureData,
            borderColor:'rgb(255,99,132)',
            tension:0.1
    },{
        labels:"Humidity",
        data:humidityData,
        borderColor:'rgb(54,162,235)',
        tension:0.1
    }]},
    option:{
        scales:{
            y:{beginAtZero:false}
        }
    }

});