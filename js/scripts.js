function wipeBrother(idBrother){
if (!confirm("Are you absolutely sure about this?")){
	return void 0;
}
	$.ajax({
	    type: 'POST',
	    url: '/wipe/'+idBrother,
	    data: null,
	    success : function (){
	    	loadBrothersList('brothers-list')
	    }
	});
}

function loadBrothersList(el){
	div = $('#'+el)	
	$.ajax({
		  url: '/admin-list',
		  success:function(data){
			  div.html(data);
		  }
		});
}